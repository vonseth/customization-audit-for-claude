"""Tests for tools/update.py and the schema version. Run: python3 -I tests/test_update.py
Builds an old and a new fake version of the project from the current files in a temp dir (fake home via
CUSTOMIZATION_AUDIT_HOME). No network: the fetcher is a fake. Neither the real home nor the real project is touched."""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
TMP = tempfile.TemporaryDirectory()
W = Path(TMP.name).resolve()
HOME = W / "home"
HOME.mkdir()
os.environ["CUSTOMIZATION_AUDIT_HOME"] = str(HOME)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
PY = [sys.executable, "-I", "-B"]

spec = importlib.util.spec_from_file_location("update", ROOT / "tools" / "update.py")
upd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upd)

IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".DS_Store", "*.pyc", ".update-state.json")


def copy_repo(dest):
    shutil.copytree(ROOT, dest, ignore=IGNORE)
    # empty the page, independent of whatever data the real page holds
    empty = Path(TMP.name) / "nothing.json"
    empty.write_text("{}", encoding="utf-8")
    p = subprocess.run(PY + [str(dest / "tools" / "import_data.py"), str(empty), "--replace"], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return dest


def tool(root, script, *args):
    p = subprocess.run(PY + [str(Path(root) / "tools" / script)] + [str(a) for a in args],
                       capture_output=True, text=True, cwd=str(root))
    return p.returncode, p.stdout + p.stderr


def snap(root):
    out = {}
    for cur, dirs, files in os.walk(root):
        for d in dirs:
            out[(Path(cur) / d).relative_to(root).as_posix() + "/"] = None
        for f in files:
            out[(Path(cur) / f).relative_to(root).as_posix()] = (Path(cur) / f).read_bytes()
    return out


def zip_tree(tree, dest, top="vonseth-customization-audit-for-claude-abc1234", extra=None):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for cur, dirs, files in os.walk(tree):
            for f in files:
                p = Path(cur) / f
                z.write(p, top + "/" + p.relative_to(tree).as_posix())
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return dest


def call(root, *args, answer="", fetcher=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = upd.main(list(args), root=root, fetcher=fetcher, stdin=io.StringIO(answer))
    return rc, out.getvalue() + err.getvalue()


def blocks(root):
    sd = upd.load_modules(Path(root) / "tools")
    return upd.strip_version(upd.read_blocks_lenient(sd, (Path(root) / "audit-overview.html").read_text(encoding="utf-8")))


# ---- schema_version basics on the current files
import re as _re
assert _re.fullmatch(r"\d+\.\d+\.\d+", (ROOT / "VERSION").read_text().strip())
sch = upd.load_modules(ROOT / "tools").SCHEMA
assert sch.version_of({"meta": {"as_of": None}}) == 0 and sch.migrate({"meta": {"as_of": None}}, 0)["meta"]["schema_version"] == 1
try:
    sch.migrate({"meta": {}}, 2)
    raise AssertionError("newer schema accepted")
except ValueError:
    pass
sample = json.loads((ROOT / "examples" / "sample-data.json").read_text(encoding="utf-8"))
assert sample["meta"]["schema_version"] == sch.CURRENT
S = W / "schema"
copy_repo(S)
page = S / "audit-overview.html"
txt = page.read_text(encoding="utf-8")
bad = txt.replace('"schema_version": 1', '"schema_version": 99')
page.write_text(bad, encoding="utf-8")
rc, out = tool(S, "build_overview.py")
assert rc == 1 and "newer than these tools" in out, out
page.write_text(txt.replace(', "schema_version": 1', ''), encoding="utf-8")  # old data without a version
assert tool(S, "build_overview.py")[0] == 0 and tool(S, "check_overview.py")[0] == 0
old_export = S / "old.json"
sample_nov = dict(sample, meta={"as_of": "2026-01-15", "sample": True})  # export of a 1.3.0 page
old_export.write_text(json.dumps(sample_nov), encoding="utf-8")
assert tool(S, "import_data.py", old_export, "--replace")[0] == 0
assert '"schema_version": 1' in page.read_text(encoding="utf-8"), "import must migrate to schema 1"
new_export = S / "new.json"
assert tool(S, "import_data.py", "--export", new_export)[0] == 0
assert json.loads(new_export.read_text())["meta"]["schema_version"] == 1
assert tool(S, "sample_data.py", "status")[0] == 0
assert tool(S, "sample_data.py", "remove")[0] == 0  # a page with only the version stamp is "empty"
assert tool(S, "sample_data.py", "load")[0] == 0 and tool(S, "sample_data.py", "remove")[0] == 0
print("schema: OK")

# ---- old and new fake versions
NEW = copy_repo(W / "new_tree")
(NEW / "VERSION").write_text("1.4.0\n")
(NEW / "tools" / "check_versions.py").write_text(
    (NEW / "tools" / "check_versions.py").read_text(encoding="utf-8") + "\n# changed in the new version\n", encoding="utf-8")
(NEW / "tests" / "test_mcp_cost.py").unlink()  # removed managed file
ZIP_NEW = zip_tree(NEW, W / "new.zip")

# failing variant: the new build_overview.py exits 1
FAIL = copy_repo(W / "fail_tree")
(FAIL / "tools" / "build_overview.py").write_text("import sys\nprint('ERROR: forced failure')\nsys.exit(1)\n")
ZIP_FAIL = zip_tree(FAIL, W / "fail.zip")

# older zip (downgrade)
OLDV = copy_repo(W / "oldv_tree")
(OLDV / "VERSION").write_text("1.2.0\n")
ZIP_DOWN = zip_tree(OLDV, W / "down.zip")

# slip zip
ZIP_SLIP = zip_tree(NEW, W / "slip.zip", extra={"../evil.txt": "x"})


def make_old(path):
    proj = copy_repo(path)
    (proj / "VERSION").write_text("1.3.0\n")
    rules = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    rules = re.sub(r"<!-- USER:(START|END) \w+ -->\n", "", rules)
    rules = rules.replace("| | | |", "| my-plugin | keep, my own decision line | 2026-11-20 |")
    rules = rules.replace("Status: not started.", "Status: my own status line.")
    (proj / "CLAUDE.md").write_text(rules, encoding="utf-8")
    p = proj / "audit-overview.html"
    assert tool(proj, "sample_data.py", "load")[0] == 0
    p.write_text(p.read_text(encoding="utf-8").replace(', "schema_version": 1', ""), encoding="utf-8")
    assert tool(proj, "build_overview.py")[0] == 0
    (proj / "reports" / "audit-report.md").write_text("# my report\n", encoding="utf-8")
    (proj / "my-notes.txt").write_text("extra user file\n", encoding="utf-8")
    assert '"schema_version"' not in p.read_text(encoding="utf-8")
    return proj


# ---- check with a fake fetcher
def release(tag, body="* new thing\n", zipball="https://api.github.com/repos/x/y/zipball/" + "v1.4.0"):
    return json.dumps({"tag_name": tag, "body": body, "published_at": "2026-11-21T10:00:00Z",
                       "html_url": "https://github.com/x/y/releases/tag/" + tag, "zipball_url": zipball}).encode()


def fake(answer):
    def f(url, accept="", timeout=10):
        if isinstance(answer, Exception):
            raise answer
        return answer(url) if callable(answer) else answer
    return f


C = make_old(W / "check_proj")
before = snap(C)
rc, out = call(C, "check", fetcher=fake(release("v1.3.0")))
assert rc == 0 and "up to date" in out.lower(), out
rc, out = call(C, "check", fetcher=fake(release("v1.4.0")))
assert rc == 0 and "newer version is available" in out and "* new thing" in out and "1.3.0" in out, out
rc, out = call(C, "check", fetcher=fake(OSError("no connection (test)")))
assert rc == 0 and "Could not check" in out and "Traceback" not in out, out
rc, out = call(C, "check", fetcher=fake(b"not json"))
assert rc == 0 and "Could not check" in out, out
assert snap(C) == before
print("check: OK")

# ---- apply: refused or cancelled cases leave the folder byte-identical
P = make_old(W / "proj")
before = snap(P)
rc, out = call(P, "apply", str(ZIP_NEW), answer="n\n")
assert rc == 1 and "Cancelled" in out and "replaced" in out and "my-notes.txt" in out and "removed" in out, out
assert snap(P) == before and not (HOME / ".claude" / "backups").exists()
rc, out = call(P, "apply", str(ZIP_NEW), answer="")
assert rc == 1 and snap(P) == before
rc, out = call(P, "apply", str(ZIP_SLIP), "--yes")
assert rc == 1 and "outside" in out and not (W / "evil.txt").exists() and snap(P) == before, out
rc, out = call(P, "apply", str(ZIP_DOWN), "--yes")
assert rc == 1 and "older" in out and snap(P) == before, out
rc, out = call(P, "apply", str(W / "nope.zip"), "--yes")
assert rc == 1 and snap(P) == before
rc, out = call(P, "apply", "--bogus")
assert rc == 2
print("refusals: OK")

# forced failure: new build_overview exits 1 -> automatic restore, byte-identical
rc, out = call(P, "apply", str(ZIP_FAIL), "--yes")
assert rc == 1 and "failed" in out and "Restored" in out, out
assert snap(P) == before, "folder differs after the automatic restore"
assert not (P / ".update-state.json").exists()
print("failure restore: OK")

# ---- successful update, then rollback
rc, out = call(P, "apply", str(ZIP_NEW), answer="y\n")
assert rc == 0, out
assert "Updated from 1.3.0 to 1.4.0" in out, out
new_m = upd.managed_files(NEW)
for rel, src in new_m.items():
    assert (P / rel).read_bytes() == src.read_bytes(), "not replaced: " + rel
assert not (P / "tests" / "test_mcp_cost.py").exists(), "removed managed file still there"
assert (P / "VERSION").read_text().strip() == "1.4.0"
ref = make_old(W / "ref_proj")
assert blocks(P) == blocks(ref), "data blocks changed"
assert '"schema_version": 1' in (P / "audit-overview.html").read_text(encoding="utf-8")
assert (P / "reports" / "audit-report.md").read_text(encoding="utf-8") == "# my report\n"
assert (P / "my-notes.txt").read_text(encoding="utf-8") == "extra user file\n"
rules = (P / "CLAUDE.md").read_text(encoding="utf-8")
assert "keep, my own decision line" in rules and "Status: my own status line." in rules, rules
assert "<!-- USER:START decisions -->" in rules and "<!-- USER:END status -->" in rules
assert "Status: not started." not in rules
new_rules = (NEW / "CLAUDE.md").read_text(encoding="utf-8")
assert rules.split("<!-- USER:START decisions -->")[0] == new_rules.split("<!-- USER:START decisions -->")[0]
assert tool(P, "check_overview.py")[0] == 0 and tool(P, "build_overview.py")[1].strip().endswith("unchanged")
st = json.loads((P / ".update-state.json").read_text())
assert st["from"] == "1.3.0" and st["to"] == "1.4.0" and (HOME / ".claude" / "backups" / st["backup"]).is_dir()
assert not any("__pycache__" in k for k in snap(P))
print("apply: OK")

# update again: now the page already has the markers (second run needs a newer zip)
rc, out = call(P, "apply", str(ZIP_NEW), "--yes")
assert rc == 0 and "Already at version 1.4.0" in out, out

rc, out = call(P, "rollback", answer="n\n")
assert rc == 1 and (P / "VERSION").read_text().strip() == "1.4.0"
rc, out = call(P, "rollback", answer="y\n")
assert rc == 0, out
assert snap(P) == before, "rollback is not byte-identical"
rc, out = call(P, "rollback", "--yes")
assert rc == 1 and "nothing to roll back" in out
print("rollback: OK")

# ---- apply without a zip: fetcher serves release and zipball
def served(url):
    if url.endswith("/releases/latest"):
        return release("v1.4.0")
    if url.endswith("/zipball/v1.4.0"):
        return ZIP_NEW.read_bytes()
    raise OSError("unexpected URL " + url)


rc, out = call(P, "apply", "--yes", fetcher=fake(served))
assert rc == 0 and "Updated from 1.3.0 to 1.4.0" in out, out
assert (P / "VERSION").read_text().strip() == "1.4.0"
rc, out = call(P, "apply", "--yes", fetcher=fake(OSError("no connection (test)")))
assert rc == 1 and "could not download" in out, out
print("apply via fetcher: OK")

# ---- git checkout: apply refused (nothing overwritten), migrate works
G = make_old(W / "git_proj")
(G / ".git").mkdir()
(G / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
before = snap(G)
rc, out = call(G, "apply", str(ZIP_NEW), "--yes")
assert rc == 1 and "git pull" in out and "migrate" in out and snap(G) == before, out
rc, out = call(G, "migrate", answer="n\n")
assert rc == 1 and snap(G) == before
rc, out = call(G, "migrate", "--yes")
assert rc == 0, out
assert '"schema_version": 1' in (G / "audit-overview.html").read_text(encoding="utf-8")
rules = (G / "CLAUDE.md").read_text(encoding="utf-8")
assert "<!-- USER:START decisions -->" in rules and "keep, my own decision line" in rules
after = snap(G)
changed = sorted(k for k in after if after[k] != before.get(k))
assert changed == ["CLAUDE.md", "audit-overview.html"], changed
rc, out = call(G, "migrate", "--yes")
assert rc == 0 and "Nothing to migrate" in out and snap(G) == after, out
print("git and migrate: OK")

# ---- http_fetch refuses non-https and keeps the token out of messages
os.environ["GITHUB_TOKEN"] = "SECRET-TOKEN-VALUE"
try:
    upd.http_fetch("http://example.invalid/x")
    raise AssertionError("http accepted")
except OSError as e:
    assert "SECRET-TOKEN-VALUE" not in str(e)
del os.environ["GITHUB_TOKEN"]
# ---- preview wording
Q = make_old(W / "preview_proj")
rc, out = call(Q, "apply", str(ZIP_NEW), answer="n\n")
assert "files you added inside managed folders" in out and "they are in the backup" in out, out
assert "Only text between the USER markers in CLAUDE.md is kept" in out and "Text outside the markers is replaced." in out, out

# ---- redirects to non-https are refused whatever the host
class _Req:
    full_url = "https://api.github.com/x"
    headers = {}
    unredirected_hdrs = {}
    def get_method(self):
        return "GET"
for target in ("http://api.github.com/y", "http://evil.invalid/y", "ftp://api.github.com/y"):
    try:
        upd._SameHostAuth().redirect_request(_Req(), None, 302, "Found", {}, target)
        raise AssertionError("redirect accepted: " + target)
    except OSError as e:
        assert "non-https" in str(e)
print("redirects: OK")

# ---- size limits (limits patched small; same code path as the real 200 MB / 10,000)
Z = W / "limits"
Z.mkdir()
big = zip_tree(NEW, Z / "big.zip")
total = sum(i.file_size for i in zipfile.ZipFile(big).infolist())
members = len(zipfile.ZipFile(big).infolist())
old_limits = (upd.MAX_ZIP_BYTES, upd.MAX_ZIP_MEMBERS)
try:
    upd.MAX_ZIP_BYTES = total - 1
    try:
        upd.safe_extract(big, Z / "out1")
        raise AssertionError("oversized archive accepted")
    except upd.Stop as e:
        assert "uncompressed" in str(e)
        assert not (Z / "out1").exists() or not list((Z / "out1").glob("*"))
    P3 = make_old(W / "limit_proj")
    b3 = snap(P3)
    rc, out = call(P3, "apply", "--yes", fetcher=fake(lambda url: release("v1.4.0") if url.endswith("/latest") else b"x" * (total)))
    assert rc == 1 and "larger than" in out and snap(P3) == b3, out
    upd.MAX_ZIP_BYTES, upd.MAX_ZIP_MEMBERS = old_limits[0], members - 1
    try:
        upd.safe_extract(big, Z / "out2")
        raise AssertionError("archive with too many members accepted")
    except upd.Stop as e:
        assert "members" in str(e)
    upd.MAX_ZIP_MEMBERS = members
    assert upd.safe_extract(big, Z / "out3").is_dir()
finally:
    upd.MAX_ZIP_BYTES, upd.MAX_ZIP_MEMBERS = old_limits
print("size limits: OK")

# ---- a destination that is a symlink is replaced, never written through
SL = make_old(W / "symlink_proj")
outside = W / "outside.txt"
outside.write_text("precious outside content\n", encoding="utf-8")
victim = SL / "tools" / "check_versions.py"
victim.unlink()
os.symlink(outside, victim)
rc, out = call(SL, "apply", str(ZIP_NEW), "--yes")
assert rc == 0, out
assert outside.read_text(encoding="utf-8") == "precious outside content\n", "update wrote through a symlink"
assert not victim.is_symlink() and victim.read_bytes() == (NEW / "tools" / "check_versions.py").read_bytes()
print("symlink: OK")

print("test_update: all checks passed")
