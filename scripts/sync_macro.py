"""Synchronize six macro topics. Stage all outputs before replacing any snapshot."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile

import macro_common
from macro_catalog import SERIES, TOPICS, topic_series
from macro_common import observation
from macro_render import ROOT, load_topic, render

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


def merge(previous, current, keys):
    validate(current, keys)
    if previous:
        validate(previous, keys)
    fresh = {(r["series_id"], r["period"]): r for r in current}
    # Rolling sources keep history before their current window. Missing known
    # observations within the window (including its former end) fail closed.
    for key in keys:
        new = [r["period"] for r in current if r["series_id"] == key]
        for old in previous:
            if old["series_id"] == key and (key not in ROLLING or old["period"] >= min(new)) and (key, old["period"]) not in fresh:
                raise ValueError(f"Source withdrew known observation {key}/{old['period']}")
    merged = {(r["series_id"], r["period"]): r for r in previous}
    merged.update(fresh)
    return sorted(merged.values(), key=lambda r: (r["series_id"], r["period"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--cache-dir", help="Development only: reuse source responses; never used by scheduled sync")
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--font")
    args = parser.parse_args()
    macro_common.CACHE = args.cache_dir
    fetched, acquisition = [], {}
    if not args.render_only:
        from macro_nbs import collect_json, collect_income
        from macro_pbc import collect
        for collector in (collect_json, collect_income, collect):
            rows, details = collector()
            fetched.extend(rows)
            acquisition.update(details)
        validate(fetched, SERIES)
    with tempfile.TemporaryDirectory(prefix="finance-macro-") as temporary:
        staging = Path(temporary)
        for slug, topic in TOPICS.items():
            keys = topic_series(topic)
            path = ROOT / f"data/macro/{slug}.csv"
            old, old_meta = load_topic(slug) if path.exists() else ([], {})
            if args.render_only:
                rows, meta = old, old_meta
                validate(rows, keys)
            else:
                rows = merge(old, [r for r in fetched if r["series_id"] in keys], keys)
                meta = dict(schema_version=1, title=topic["title"], series={k: SERIES[k] for k in keys},
                            acquisition={k: acquisition[k] for k in keys})
                old_compare = {k: v for k, v in old_meta.items() if k != "retrieved_at"}
                meta["retrieved_at"] = old_meta["retrieved_at"] if old == rows and old_compare == meta else datetime.now(timezone.utc).isoformat(timespec="seconds")
            directory = staging / "data/macro"
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / f"{slug}.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            (directory / f"{slug}.metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            render(slug, rows, meta, staging, args.font, args.preview_dir)
            print(slug, len(rows), "observations rendered", flush=True)
        # No source/parser/render failure can leave a partially refreshed snapshot.
        for source in staging.rglob("*"):
            if source.is_file():
                destination = ROOT / source.relative_to(staging)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists() or source.read_bytes() != destination.read_bytes():
                    shutil.copyfile(source, destination)


if __name__ == "__main__":
    main()
