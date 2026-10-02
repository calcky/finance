"""Transient source errors must not destroy history or block unrelated topics."""

from copy import deepcopy
from http.client import RemoteDisconnected, IncompleteRead
from io import BytesIO
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import macro_common
from macro_catalog import SERIES
from macro_common import observation
import source_http
import sync_data
import sync_macro

URL = "https://example.org/history?start=1950"


class HttpRecovery(unittest.TestCase):
    def test_disconnect_and_read_timeout_recover_with_same_request(self):
        for error in (RemoteDisconnected("closed"), TimeoutError("timed out"),
                      URLError(ConnectionResetError("reset")), IncompleteRead(b"part", 8),
                      HTTPError(URL, 503, "Unavailable", {}, None)):
            with self.subTest(error=type(error).__name__):
                opener = Mock(side_effect=[error, BytesIO(b"complete")])
                request = Request(URL)
                with patch.object(source_http.time, "sleep") as sleep:
                    self.assertEqual(source_http.read(request, opener), b"complete")
                self.assertEqual(opener.call_count, 2)
                self.assertIs(opener.call_args_list[0].args[0], opener.call_args_list[1].args[0])
                sleep.assert_called_once_with(2)

    def test_failure_is_bounded_and_exposes_url(self):
        opener = Mock(side_effect=RemoteDisconnected("closed"))
        with patch.object(source_http.time, "sleep") as sleep:
            with self.assertRaises(RemoteDisconnected) as context:
                source_http.read(Request(URL), opener)
        self.assertEqual(opener.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])
        self.assertIn(URL, source_http.describe(context.exception))

    def test_refusal_rate_limit_and_tls_failure_are_not_retried(self):
        errors = [HTTPError(URL, code, "Refused", {}, None) for code in (400, 401, 403, 404, 429)]
        errors.append(URLError(ssl.SSLCertVerificationError("certificate")))
        for error in errors:
            opener = Mock(side_effect=error)
            with self.assertRaises(type(error)):
                source_http.read(Request(URL), opener)
            self.assertEqual(opener.call_count, 1)

    def test_partial_response_is_never_cached(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(macro_common, "CACHE", temporary), \
             patch.object(macro_common.OPENER, "open", side_effect=IncompleteRead(b"broken", 3)), \
             patch.object(source_http.time, "sleep"):
            with self.assertRaises(IncompleteRead):
                macro_common.fetch(URL)
            self.assertEqual(list(Path(temporary).iterdir()), [])


class TopicIsolation(unittest.TestCase):
    def test_unknown_source_series_is_not_silently_filtered_away(self):
        rows = [observation("cpi_yoy", "2026-01", 1, URL)]
        unknown = dict(rows[0], series_id="unknown_series")
        collector = Mock(return_value=(rows + [unknown], {}))
        collector.__module__ = "changed_source"
        topics = {"prices": dict(charts=[dict(series=["cpi_yoy"])])}
        with patch.object(sync_macro, "collectors_for", return_value=[collector]):
            batches, errors = sync_macro.collect_independent(topics, False)
        self.assertEqual(batches, {})
        self.assertIn("unknown_series", errors["prices"])

    def test_shared_collector_runs_once_and_only_blocks_dependants(self):
        shared = Mock(side_effect=RemoteDisconnected("closed"))
        shared.__module__ = "shared_source"
        separate = Mock(return_value=([observation("ppi_yoy", "2026-01", 1, URL)], {}))
        separate.__module__ = "other_source"
        topics = {k: dict(charts=[dict(series=[v])]) for k, v in (("a", "cpi_yoy"), ("b", "cpi_yoy"), ("c", "ppi_yoy"))}
        def discover(slugs):
            return [separate if next(iter(slugs)) == "c" else shared]
        with patch.object(sync_macro, "collectors_for", side_effect=discover):
            batches, errors = sync_macro.collect_independent(topics, False)
        shared.assert_called_once_with(backfill=False)
        separate.assert_called_once_with(backfill=False)
        self.assertEqual(set(errors), {"a", "b"})
        self.assertEqual(set(batches), {"c"})

    def run_update(self, failure):
        topics = {k: dict(title=k, charts=[dict(series=[k])]) for k in ("cpi_yoy", "ppi_yoy")}
        rows = {k: [observation(k, "2026-01", 1, URL)] for k in topics}
        metadata = {k: dict(refresh_ranges=[dict(start="2026-01", end="2026-01")]) for k in topics}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(dict(rows=[r for batch in rows.values() for r in batch], meta=metadata)))
            report = root / "attempt.json"
            def render(slug, data, meta, staging, *args):
                path = staging / f"docs/data/{slug}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(data[0]["value"])
                if failure == "render" and slug == "ppi_yoy" and data[0]["value"] != "1":
                    raise ValueError("broken renderer")
            def invoke(*args):
                with patch.object(sys, "argv", ["sync_macro", *args]):
                    return sync_macro.main()
            with patch.object(sync_macro, "ROOT", root), patch.object(sync_macro, "TOPICS", topics), \
                 patch.object(sync_macro, "SERIES", {k: SERIES[k] for k in topics}), \
                 patch.object(sync_macro, "render", side_effect=render):
                self.assertEqual(invoke("--source-snapshots", str(source), "--backfill"), 0)
                before = {p.relative_to(root): p.read_bytes() for base in ("data", "docs") for p in (root / base).rglob("*") if p.is_file()}
                revised = deepcopy(rows)
                for batch in revised.values():
                    batch[0]["value"] = "2"
                def good(backfill):
                    return revised["cpi_yoy"], {"cpi_yoy": metadata["cpi_yoy"]}
                def bad(backfill):
                    if failure == "fetch":
                        raise RemoteDisconnected("closed")
                    batch = [] if failure == "validation" else revised["ppi_yoy"]
                    return batch, {"ppi_yoy": metadata["ppi_yoy"]}
                with patch.object(sync_macro, "collectors_for", side_effect=lambda slugs: [good if "cpi_yoy" in slugs else bad]):
                    self.assertEqual(invoke("--keep-going", "--report", str(report)), 1)
                after = {p: (root / p).read_bytes() for p in before}
                for path in before:
                    if "ppi_yoy" in str(path):
                        self.assertEqual(after[path], before[path])
                self.assertEqual((root / "docs/data/cpi_yoy.md").read_text(), "2")
                self.assertEqual(json.loads(report.read_text())["ppi_yoy"]["state"], "failed")
                self.assertEqual(json.loads(report.read_text())["cpi_yoy"]["state"], "ok")

    def test_fetch_failure_preserves_only_affected_topic(self):
        self.run_update("fetch")

    def test_validation_failure_preserves_only_affected_topic(self):
        self.run_update("validation")

    def test_partial_render_never_reaches_publication(self):
        self.run_update("render")


class StatusReporting(unittest.TestCase):
    def test_failed_snapshot_has_visible_warning_and_escaped_link(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("docs_conf", sync_data.ROOT / "docs/conf.py")
        conf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(conf)
        context = dict(body="<article>saved chart</article>", pathto=lambda _: 'status.html?x="')
        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value=json.dumps({"gdp": dict(state="failed")})):
            conf.add_sync_status(None, "data/gdp", None, context, None)
        self.assertIn('class="admonition warning sync-status"', context["body"])
        self.assertIn("上次有效快照", context["body"])
        self.assertIn("&quot;", context["body"])
        self.assertTrue(context["body"].endswith("<article>saved chart</article>"))

    def test_noop_checks_do_not_change_timestamps_and_recovery_is_visible(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sync_data, "TITLES", {"gdp": "GDP"}):
            root = Path(temporary)
            (root / "data").mkdir()
            (root / "data/gdp.metadata.json").write_text(json.dumps(dict(retrieved_at="2026-01-01")))
            sync_data.update_status({}, root, "first")
            self.assertIn("尚未记录", (root / "docs/data/update-status.md").read_text())
            sync_data.update_status({"gdp": dict(state="ok")}, root, "first")
            files = [root / "data/update-status.json", root / "docs/data/update-status.md"]
            before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in files]
            sync_data.update_status({"gdp": dict(state="ok")}, root, "later")
            self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in files])
            sync_data.update_status({"gdp": dict(state="failed", error="disconnect")}, root, "failure")
            self.assertIn("disconnect", files[1].read_text())
            result = sync_data.update_status({"gdp": dict(state="ok")}, root, "recovery")
            self.assertEqual(result["gdp"]["state_since"], "recovery")
            self.assertNotIn("disconnect", files[1].read_text())
            self.assertEqual(result["gdp"]["snapshot_at"], "2026-01-01")

    def test_gdp_failure_does_not_prevent_macro_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            def fake_run(command, log):
                log.write_text("source disconnected\n")
                if "sync_gdp.py" in command[2]:
                    return 1
                (directory / "macro.json").write_text(json.dumps({k: dict(state="ok") for k in sync_data.TOPICS}))
                return 0
            with patch.object(sync_data, "run", side_effect=fake_run) as run, \
                 patch.object(sync_data, "update_status") as status, patch.dict(sync_data.os.environ, {}, clear=True), \
                 patch("builtins.print"):
                self.assertEqual(sync_data.attempt(directory, False), 1)
            self.assertEqual(run.call_count, 2)
            outcomes = status.call_args.args[0]
            self.assertEqual(outcomes["gdp"]["state"], "failed")
            self.assertTrue(all(outcomes[k]["state"] == "ok" for k in sync_data.TOPICS))


if __name__ == "__main__":
    unittest.main()
