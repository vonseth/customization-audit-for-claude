#!/usr/bin/env python3
"""Tests for tools/check_versions.py. Run: python3 -I tests/test_check_versions.py

Builds a fake home with a fake marketplace (a small git repo with two commits
when git is available) and checks the three statuses plus the version path.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import check_versions  # noqa: E402

HAVE_GIT = shutil.which("git") is not None


def git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false"] + list(a), check=True, capture_output=True)


def head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class CheckVersions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_env = os.environ.get("CUSTOMIZATION_AUDIT_HOME")
        os.environ["CUSTOMIZATION_AUDIT_HOME"] = self.tmp
        self.plugins = Path(self.tmp) / ".claude" / "plugins"
        self.mkt = self.plugins / "marketplaces" / "mk"

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("CUSTOMIZATION_AUDIT_HOME", None)
        else:
            os.environ["CUSTOMIZATION_AUDIT_HOME"] = self.old_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, entries, installed, commit_based):
        write(self.mkt / ".claude-plugin" / "marketplace.json",
              json.dumps({"name": "mk", "plugins": entries}))
        for e in entries:
            if isinstance(e["source"], str):
                pj = {"name": e["name"]}
                if e["name"] in commit_based.get("versioned", {}):
                    pj["version"] = commit_based["versioned"][e["name"]]
                write(self.mkt / e["source"] / ".claude-plugin" / "plugin.json", json.dumps(pj))
        write(self.plugins / "known_marketplaces.json", json.dumps(
            {"mk": {"source": {"source": "github", "repo": "me/mk"},
                    "installLocation": str(self.mkt), "lastUpdated": "2026-01-01T00:00:00Z"}}))
        write(self.plugins / "installed_plugins.json", json.dumps({"version": 2, "plugins": installed}))

    def result(self, out, name):
        return [r for r in out["plugins"] if r["name"] == name][0]

    def test_versions(self):
        entries = [{"name": "a", "source": "./a"}, {"name": "b", "source": "./b"},
                   {"name": "c", "source": {"source": "url", "url": "x"}}]
        inst = {"a@mk": [{"version": "1.0.0"}], "b@mk": [{"version": "1.0.0"}],
                "c@mk": [{"version": "1.0.0"}]}
        self.build(entries, inst, {"versioned": {"a": "1.0.0", "b": "1.2.0"}})
        out = check_versions.run()
        self.assertEqual(self.result(out, "a")["status"], check_versions.UP)
        self.assertEqual(self.result(out, "b")["status"], check_versions.NEWER)
        r = self.result(out, "c")
        self.assertEqual(r["status"], check_versions.UNKNOWN)
        self.assertTrue(r["reason"])
        self.assertEqual(out["marketplaces"][0]["last_updated"], "2026-01-01T00:00:00Z")

    @unittest.skipUnless(HAVE_GIT, "git not available")
    def test_commits(self):
        entries = [{"name": "p1", "source": "./p1"}, {"name": "p2", "source": "./p2"},
                   {"name": "p3", "source": "./p3"}]
        for n in ("p1", "p2", "p3"):
            write(self.mkt / n / "f.txt", "one")
        write(self.mkt / ".claude-plugin" / "marketplace.json", json.dumps({"name": "mk", "plugins": entries}))
        subprocess.run(["git", "init", "-q", str(self.mkt)], check=True)
        git(self.mkt, "add", "-A")
        git(self.mkt, "commit", "-qm", "one")
        first = head(self.mkt)
        write(self.mkt / "p2" / "f.txt", "two")  # only p2 changes
        git(self.mkt, "add", "-A")
        git(self.mkt, "commit", "-qm", "two")
        inst = {"p1@mk": [{"version": first[:12], "gitCommitSha": first}],       # unchanged -> up to date
                "p2@mk": [{"version": first[:12], "gitCommitSha": first}],       # changed -> newer
                "p3@mk": [{"version": "x", "gitCommitSha": "0" * 40}]}           # unknown commit
        self.build(entries, inst, {})
        out = check_versions.run()
        self.assertEqual(self.result(out, "p1")["status"], check_versions.UP)
        r = self.result(out, "p2")
        self.assertEqual(r["status"], check_versions.NEWER)
        self.assertIn("/compare/", r["history"])
        self.assertEqual(self.result(out, "p3")["status"], check_versions.UNKNOWN)

    def test_main_json_and_missing(self):
        # no installed_plugins.json: note on stderr, empty result, exit 0
        import contextlib
        import io
        for argv in (["--json"], []):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = check_versions.main(argv)
            self.assertEqual(rc, 0)
            self.assertIn("no local plugins found", err.getvalue())
            if argv:
                self.assertEqual(json.loads(out.getvalue()), {"plugins": [], "marketplaces": []})
        # exists but broken: still an error
        write(self.plugins / "installed_plugins.json", "not json")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_versions.main(["--json"]), 2)

    def test_version_compare(self):
        def newer(a, b):
            return check_versions.older(check_versions.vkey(a), check_versions.vkey(b))
        self.assertTrue(newer("2.0.0-beta.1", "2.0.0"))
        self.assertFalse(newer("2.0.0", "2.0.0-beta.1"))
        self.assertFalse(newer("2.0.0+build5", "2.0.0"))
        self.assertFalse(newer("1.2", "1.2.0"))
        self.assertFalse(newer("1.2.0", "1.2"))
        self.assertTrue(newer("1.2", "1.2.1"))
        self.assertTrue(newer("1.9.9", "1.10"))
        self.assertTrue(newer("1.0.0-beta.2", "1.0.1-beta.1"))
        self.assertIsNone(check_versions.vkey("abc"))

    def test_prerelease_status(self):
        entries = [{"name": "a", "source": "./a"}]
        self.build(entries, {"a@mk": [{"version": "2.0.0-beta.1"}]}, {"versioned": {"a": "2.0.0"}})
        self.assertEqual(self.result(check_versions.run(), "a")["status"], check_versions.NEWER)


if __name__ == "__main__":
    unittest.main(verbosity=2)
