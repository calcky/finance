"""Synchronize macro topics. Stage all outputs before replacing any snapshot."""

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile

import macro_common
from macro_catalog import SERIES, TOPICS, topic_series
from macro_common import observation
from macro_render import ROOT, load_topic, render
from source_http import describe

FIELDS = ["series_id", "country", "period", "value", "unit", "frequency", "published_at", "source_url", "note"]
ROLLING = {"repo_7d", "yield_1y", "yield_10y", "usdcny_mid"}


def validate(rows, keys):
    seen = set()
    for row in rows:
        key = row["series_id"]
        identity = (key, row["period"])
        if key not in keys or identity in seen or row["country"] != "CHN":
            raise ValueError(f"Unknown/duplicate observation: {identity}")
        seen.add(identity)
        checked = observation(key, row["period"], row["value"], row["source_url"], row["published_at"], row["note"])
        if checked is None or checked["unit"] != row["unit"] or checked["frequency"] != row["frequency"]:
            raise ValueError("Empty or inconsistent observation")
    if {r["series_id"] for r in rows} != set(keys):
        raise ValueError("Missing entire series")


def merge(previous, current, keys, refresh_ranges=None):
    current_keys = {r["series_id"] for r in current}
    validate(current, current_keys if refresh_ranges is not None else keys)
    if previous:
        validate(previous, {r["series_id"] for r in previous})
    fresh = {(r["series_id"], r["period"]): r for r in current}
    # Rolling sources keep history before their current window. Missing known
    # observations within the window (including its former end) fail closed.
    for key in keys:
        new = [r["period"] for r in current if r["series_id"] == key]
        for old in previous:
            covered = (key not in ROLLING or (new and old["period"] >= min(new))) if refresh_ranges is None else any(
                span["start"] <= old["period"] <= span["end"] for span in refresh_ranges.get(key, []))
            if old["series_id"] == key and covered and (key, old["period"]) not in fresh:
                raise ValueError(f"Source withdrew known observation {key}/{old['period']}")
    merged = {(r["series_id"], r["period"]): r for r in previous}
    merged.update(fresh)
    return sorted(merged.values(), key=lambda r: (r["series_id"], r["period"]))


def combine(batches):
    """Only identical overlaps can merge; conflicting sources need explicit policy."""
    observations, metadata = {}, {}
    for rows, details in batches:
        if not isinstance(details, dict):
            raise ValueError("Missing collector metadata")
        for key, detail in details.items():
            if detail.get("requested_window_complete") is False or detail.get("failed_urls"):
                raise ValueError(f"Incomplete source crawl: {key}")
        for row in rows:
            identity = row["series_id"], row["period"]
            old = observations.get(identity)
            if old and Decimal(old["value"]) != Decimal(row["value"]):
                raise ValueError(f"Conflicting source observations: {identity}")
            observations[identity] = row
        for key, detail in details.items():
            if key not in metadata:
                metadata[key] = detail
            else:
                old = metadata[key]
                metadata[key] = dict(old, refresh_ranges=old.get("refresh_ranges", []) + detail.get("refresh_ranges", []),
                                     supplemental_sources=old.get("supplemental_sources", []) + [detail])
    return list(observations.values()), metadata


def trade_reconciliation(rows):
    """Expose reported-vs-calculated source differences; never alter the quote."""
    values = {(r["series_id"], r["period"]): Decimal(r["value"]) for r in rows}
    differences = []
    for period in sorted(p for key, p in values if key == "trade_balance"):
        triple = [values[key, period] for key in ("exports", "imports", "trade_balance")]
        exports, imports, reported = triple
        residual = exports - imports - reported
        precision = sum(Decimal(10) ** v.normalize().as_tuple().exponent / 2 for v in triple)
        if abs(residual) > precision:
            differences.append(dict(period=period, exports=str(exports), imports=str(imports),
                                    reported_balance=str(reported), calculated_balance=str(exports-imports),
                                    residual=str(residual), unit="亿美元"))
    return differences


def needs_history(meta, now):
    stamps = [datetime.fromisoformat(meta[k]) for k in ("retrieved_at", "history_checked_at") if meta.get(k)]
    return not meta.get("history") or not stamps or (now - max(stamps)).days >= 60


def collectors_for(topics):
    from macro_nbs_history import collect as nbs
    from macro_income_history import collect as income
    from macro_money_history import collect as money
    from macro_market_history import collect as market
    from macro_repo_history import collect as repo
    from macro_nbs_cpi_releases import collect as cpi_releases
    from macro_quarterly_gdp import collect as quarterly_gdp
    from macro_tsf_components import collect as tsf_components
    from macro_loan_history import collect as loans
    from macro_property import collect as property_history
    from macro_population import collect as population
    from macro_shanghai import collect as shanghai
    from macro_housing import collect as housing
    from macro_housing_wealth import collect as housing_wealth
    from macro_fiscal import collect as fiscal
    groups = [(nbs, {"prices", "money-credit", "activity", "trade-fx", "employment-income"}),
              (income, {"employment-income"}), (money, {"money-credit"}),
              (market, {"rates", "trade-fx"}), (repo, {"rates"}),
              (cpi_releases, {"prices"}), (quarterly_gdp, {"quarterly-gdp"}),
              (tsf_components, {"credit-structure"}), (loans, {"credit-structure"}),
              (property_history, {"property"}), (population, {"population"}),
              (shanghai, {"shanghai-population"}), (housing, {"housing-prices"}),
              (housing_wealth, {"housing-wealth"}), (fiscal, {"fiscal"})]
    return [collector for collector, covered in groups if covered.intersection(topics)]


def collect_independent(topics, backfill):
    """Fetch shared collectors once; one failure blocks only its dependants."""
    dependencies = {slug: collectors_for({slug}) for slug in topics}
    results, failures = {}, {}
    for collector in dict.fromkeys(c for group in dependencies.values() for c in group):
        name = collector.__module__
        print(f"Collecting {name}", flush=True)
        try:
            batch = combine([collector(backfill=backfill)])
            # Validate the whole source result before selecting topic fields;
            # filtering must not silently hide unknown series or partial crawls.
            check_collection(*batch, False, {})
            results[collector] = batch
            print(f"Collected {name}", flush=True)
        except Exception as error:
            failures[collector] = f"{name}: {describe(error)}"
            print(f"Collector failed: {failures[collector]}", flush=True)
    batches, errors = {}, {}
    for slug, collectors in dependencies.items():
        failed = [failures[c] for c in collectors if c in failures]
        if failed:
            errors[slug] = "; ".join(failed)
        else:
            keys = set(topic_series(topics[slug]))
            batches[slug] = [([r for r in results[c][0] if r["series_id"] in keys],
                              {k: v for k, v in results[c][1].items() if k in keys})
                             for c in collectors]
    return batches, errors


def publish(staging):
    for source in staging.rglob("*"):
        if source.is_file():
            destination = ROOT / source.relative_to(staging)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or source.read_bytes() != destination.read_bytes():
                shutil.copyfile(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--backfill", action="store_true", help="Exhaust official history archives; slower than routine refresh")
    parser.add_argument("--source-snapshots", nargs="+", type=Path, help="Import separately verified collector outputs for a resumable initial backfill")
    parser.add_argument("--cache-dir", help="Development only: reuse source responses; never used by scheduled sync")
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--font")
    parser.add_argument("--topics", nargs="+", choices=list(TOPICS), help="Refresh only selected topics (default: all)")
    parser.add_argument("--keep-going", action="store_true", help="Publish complete topics independently; return nonzero on any failure")
    parser.add_argument("--report", type=Path, help="Write this attempt's per-topic results outside snapshot metadata")
    args = parser.parse_args()
    selected_topics = {slug: topic for slug, topic in TOPICS.items() if not args.topics or slug in args.topics}
    macro_common.CACHE = args.cache_dir
    if not args.render_only and not args.source_snapshots and not args.backfill:
        for slug in selected_topics:
            meta_path = ROOT / f"data/macro/{slug}.metadata.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            if needs_history(meta, datetime.now(timezone.utc)):
                print("Missing/stale historical snapshot: running a full backfill", flush=True)
                args.backfill = True
                break
    fetched, acquisition, independent, errors = [], {}, {}, {}
    if not args.render_only:
        if args.source_snapshots:
            batches = []
            for path in args.source_snapshots:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                batches.append((snapshot["rows"], snapshot.get("meta", snapshot.get("metadata"))))
        elif args.keep_going:
            independent, errors = collect_independent(selected_topics, args.backfill)
        else:
            batches = []
            for collector in collectors_for(selected_topics):
                print(f"Collecting {collector.__module__}", flush=True)
                batches.append(collector(backfill=args.backfill))
        if not args.keep_going or args.source_snapshots:
            fetched, acquisition = combine(batches)
            check_collection(fetched, acquisition, args.backfill, selected_topics)
    outcomes = {slug: dict(state="failed", error=error) for slug, error in errors.items()}
    with tempfile.TemporaryDirectory(prefix="finance-macro-") as temporary:
        staging = Path(temporary)
        for slug, topic in selected_topics.items():
            if slug in errors:
                continue
            target = staging / slug if args.keep_going else staging
            try:
                if independent:
                    fetched, acquisition = combine(independent[slug])
                    check_collection(fetched, acquisition, args.backfill, {slug})
                stage_topic(slug, topic, fetched, acquisition, args, target)
            except Exception as error:
                if not args.keep_going:
                    raise
                outcomes[slug] = dict(state="failed", error=describe(error))
                print(f"Topic failed {slug}: {describe(error)}", flush=True)
                continue
            # Copy only after the complete topic rendered; failed staging is discarded.
            if args.keep_going:
                publish(target)
            outcomes[slug] = dict(state="ok")
        if not args.keep_going:
            publish(staging)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(any(item["state"] == "failed" for item in outcomes.values()))


def check_collection(fetched, acquisition, backfill, topics):
    if backfill and "rates" in topics and acquisition.get("repo_7d", {}).get("complete_archive") is not True:
        raise ValueError("Full backfill requires a completed reverse-repo archive audit")
    validate(fetched, {r["series_id"] for r in fetched})
    expected = {key for topic in TOPICS.values() for key in topic_series(topic)}
    if set(SERIES) != expected or {r["series_id"] for r in fetched} - expected:
        raise ValueError("Series catalogue and topic coverage differ")


def stage_topic(slug, topic, fetched, acquisition, args, staging):
    keys = topic_series(topic)
    path = ROOT / f"data/macro/{slug}.csv"
    old, old_meta = load_topic(slug, ROOT) if path.exists() else ([], {})
    if args.render_only:
        rows, meta = old, old_meta
        validate(rows, keys)
    else:
        ranges = {k: acquisition.get(k, {}).get("refresh_ranges", []) for k in keys}
        if args.backfill:
            # A full archive audit also covers every previously saved
            # point, even if its source index/first page disappeared.
            for key in keys:
                prior_periods = [r["period"] for r in old if r["series_id"] == key]
                if prior_periods:
                    ranges[key] = ranges[key] + [{"start": min(prior_periods), "end": max(prior_periods)}]
        rows = merge(old, [r for r in fetched if r["series_id"] in keys], keys, ranges)
        validate(rows, keys)
        prior_sources = old_meta.get("acquisition", {})
        sources = {k: acquisition.get(k, prior_sources.get(k, {})) for k in keys}
        # Retain initial archive provenance when daily refresh covers a
        # smaller window; no daily timestamp churn for unchanged data.
        history = old_meta.get("history", {})
        if args.backfill:
            history = {k: sources[k] for k in keys}
        meta = dict(schema_version=2, title=topic["title"], series={k: SERIES[k] for k in keys},
                    acquisition=sources, history=history,
                    coverage={k: {"first": min(r["period"] for r in rows if r["series_id"] == k),
                                  "last": max(r["period"] for r in rows if r["series_id"] == k),
                                  "count": sum(r["series_id"] == k for r in rows)} for k in keys})
        if slug == "trade-fx":
            meta["reported_balance_differences"] = trade_reconciliation(rows)
        if args.backfill:
            meta["history_checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        elif old_meta.get("history_checked_at"):
            meta["history_checked_at"] = old_meta["history_checked_at"]
        old_compare = {k: v for k, v in old_meta.items() if k != "retrieved_at"}
        meta["retrieved_at"] = old_meta["retrieved_at"] if old == rows and old_compare == meta else datetime.now(timezone.utc).isoformat(timespec="seconds")
        # Acquisition parameters describe the saved snapshot. A new
        # check date or rolling query boundary alone is not new data;
        # successful unchanged checks remain visible in Actions logs.
        stable_fields = {k: v for k, v in meta.items() if k not in ("acquisition", "retrieved_at")}
        prior_fields = {k: v for k, v in old_meta.items() if k not in ("acquisition", "retrieved_at")}
        if not args.backfill and old == rows and prior_fields == stable_fields:
            meta = old_meta
    directory = staging / "data/macro"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{slug}.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (directory / f"{slug}.metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True) + "\n", encoding="utf-8")
    render(slug, rows, meta, staging, args.font, args.preview_dir)
    print(slug, len(rows), "observations rendered", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
