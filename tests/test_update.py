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
assert rc == 0 and "already current, nothing to migrate" in out.lower() and snap(G) == after, out
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

# ---- hardening round: each block fails on the previous code
# schema_version validation (item 6)
for badv in (-1, True, "1", 1.5):
    try:
        sch.migrate({"meta": {"schema_version": badv}}, sch.version_of({"meta": {"schema_version": badv}}))
        raise AssertionError("invalid schema_version accepted: %r" % (badv,))
    except ValueError as e:
        assert "invalid schema_version" in str(e), e
try:
    sch.migrate({"meta": {}}, sch.CURRENT + 1)
    raise AssertionError
except ValueError as e:
    assert "newer version" in str(e), e
SV = make_old(W / "schema_cli")
svp = SV / "audit-overview.html"
svp.write_text(svp.read_text(encoding="utf-8").replace('"as_of"', '"schema_version": -1, "as_of"', 1), encoding="utf-8")
(SV / ".git").mkdir()
rc, out = call(SV, "migrate", "--yes")
assert rc == 1 and "invalid schema_version" in out and "Traceback" not in out, out

# pre-release precedence (item 7)
pv = upd.parse_version
assert pv("1.5.0-beta.1") < pv("1.5.0-beta.2") < pv("1.5.0-beta.10") < pv("1.5.0") < pv("1.5.1-alpha")
assert pv("1.5.0-alpha") < pv("1.5.0-alpha.1") < pv("1.5.0-alpha.beta") < pv("1.5.0-beta")
assert pv("1.5.0-1") < pv("1.5.0-alpha") and pv("1.5.0+b1") == pv("1.5.0") and pv("v1.2") == pv("1.2.0")
assert pv("1.5.0-beta.1") != pv("1.5.0-beta.2") and pv("nonsense") is None

# a block the new version adds is missing in the old page (item 1)
M = make_old(W / "missing_block")
m_html = (M / "audit-overview.html").read_text(encoding="utf-8")
m_old = upd.read_blocks_lenient(upd.load_modules(M / "tools"), m_html)
m_old.pop("open-items")
rc_problem = upd._do_update(M, NEW, upd.plan(M, NEW), m_old, m_html, {})
assert rc_problem is None, rc_problem
assert blocks(M)["open-items"] == upd.load_modules(M / "tools").EMPTY["open-items"]

# CRLF CLAUDE.md (item 2)
crlf = ("# T\r\n<!-- USER:START decisions -->\r\nmine\r\nline2\r\n<!-- USER:END decisions -->\r\nrest\r\n"
        "## Status and open items\r\nmy status\r\n\r\n## Next\r\n")
secs, how_ = upd.extract_user_sections(crlf)
assert how_ == {"decisions": "markers", "status": "heading"} and secs["decisions"] == "mine\r\nline2\r\n", (secs, how_)
assert secs["status"].startswith("## Status and open items\r\nmy status") and secs["status"].endswith("\r\n\r\n")
merged = upd.merge_user_sections("# new\n<!-- USER:START decisions -->\nold\n<!-- USER:END decisions -->\n", secs)
assert "<!-- USER:START decisions -->\nmine\r\nline2\r\n<!-- USER:END decisions -->\n" in merged, repr(merged)
assert "my status" in merged
assert "<!-- USER:START status -->\r\n" not in merged  # markers follow the new file, text keeps its endings
wrapped = upd.add_markers("## Decisions (kept deliberately)\r\nx\r\n\r\n## Next\r\n")
assert wrapped.startswith("<!-- USER:START decisions -->\r\n## Decisions") and "<!-- USER:END decisions -->\r\n## Next" in wrapped
CR = make_old(W / "crlf_proj")
cr_rules = upd.add_markers((CR / "CLAUDE.md").read_text(encoding="utf-8")).replace("\n", "\r\n")
upd.wr(CR / "CLAUDE.md", cr_rules)
rc, out = call(CR, "apply", str(ZIP_NEW), "--yes")
assert rc == 0, out
cr_after = upd.rd(CR / "CLAUDE.md")
assert "keep, my own decision line | 2026-11-20 |\r\n" in cr_after and "Status: my own status line.\r\n" in cr_after, cr_after

# manifest validation before restore (item 3)
for bad_entry in ({"original": "relative/x", "stored": "1/x", "type": "dir"},
                  {"original": str(W / "a" / ".." / "proj"), "stored": "1/proj", "type": "dir"},
                  {"original": str(W / "proj"), "stored": "../escape", "type": "dir"},
                  {"original": str(W / "proj"), "stored": str(W / "escape"), "type": "dir"},
                  {"original": str(W / "proj"), "stored": "1/proj", "type": "link"},
                  {"original": str(W / "other"), "stored": "1/proj", "type": "dir"}):
    try:
        upd.check_entries([bad_entry], [W / "proj"], "x")
        raise AssertionError("manifest entry accepted: %r" % (bad_entry,))
    except upd.Stop:
        pass
upd.check_entries([{"original": str(W / "proj"), "stored": "1/proj", "type": "dir"}], [W / "proj"], "x")
RB = make_old(W / "rollback_proj")
rb_before = snap(RB)
rc, out = call(RB, "apply", str(ZIP_NEW), "--yes")
assert rc == 0, out
rb_state = json.loads((RB / ".update-state.json").read_text(encoding="utf-8"))
mf = HOME / ".claude" / "backups" / rb_state["backup"] / "manifest.json"
good_manifest = mf.read_text(encoding="utf-8")
man = json.loads(good_manifest)
man["entries"][0]["original"] = str(RB) + "/../" + RB.name  # same place once normalised, but not a clean path
mf.write_text(json.dumps(man), encoding="utf-8")
after_apply = snap(RB)
rc, out = call(RB, "rollback", "--yes")
assert rc == 1 and "unsafe path" in out and snap(RB) == after_apply, out
mf.write_text(good_manifest, encoding="utf-8")

# the rollback preview lists what will be removed (item 4)
(RB / "reports" / "made-after-update.md").write_text("new\n", encoding="utf-8")
after_apply = snap(RB)
rc, out = call(RB, "rollback", answer="n\n")
assert rc == 1 and snap(RB) == after_apply
assert "reports/made-after-update.md" in out and "will be removed" in out, out
assert out.index("reports/made-after-update.md") < out.index("Roll back?"), out
# a failing automatic restore names the by-hand command (item 3)
real_restore = upd.restore_backup
def _failing_restore(name, expected):
    raise upd.Stop("simulated")
upd.restore_backup = _failing_restore
try:
    upd.restore_or_hint("some-backup-2026-01-01", [RB])
    raise AssertionError("no hint")
except upd.Stop as e:
    assert "simulated" in str(e) and "backup.py" in str(e) and " restore some-backup-2026-01-01" in str(e), str(e)
finally:
    upd.restore_backup = real_restore
rc, out = call(RB, "rollback", "--yes")
assert rc == 0, out
assert not (RB / "reports" / "made-after-update.md").exists()

# migrate: a current page is left byte-identical, even if its JSON is formatted differently (item 5)
MG = make_old(W / "migrate_current")
(MG / ".git").mkdir()
assert call(MG, "migrate", "--yes")[0] == 0
mg_page = MG / "audit-overview.html"
mg_page.write_text(mg_page.read_text(encoding="utf-8").replace('"schema_version": 1', '"schema_version":1'), encoding="utf-8")
mg_before = snap(MG)
rc, out = call(MG, "migrate", "--yes")
assert rc == 0 and "already current, nothing to migrate" in out.lower() and "->" not in out, out
assert snap(MG) == mg_before, "a current page was rewritten"

# --help prints the usage to stdout and exits 0; usage errors go to stderr with exit 2 (item 10)
HELP_ROOT = make_old(W / "help_proj")
help_before = snap(HELP_ROOT)
for argv in (["--help"], ["-h"], ["apply", "--help"], ["rollback", "-h"]):
    rc, out = call(HELP_ROOT, *argv)
    assert rc == 0 and "Usage:" in out, (argv, out)
assert snap(HELP_ROOT) == help_before
p = subprocess.run(PY + [str(ROOT / "tools" / "update.py"), "--help"], capture_output=True, text=True)
assert p.returncode == 0 and "Usage:" in p.stdout and p.stderr == "", p
p = subprocess.run(PY + [str(ROOT / "tools" / "update.py"), "bogus"], capture_output=True, text=True)
assert p.returncode == 2 and p.stdout == "" and "Usage:" in p.stderr, p
print("hardening: OK")

# symlinks in a backed-up project folder are restored as links (backup.py stores them as links)
if hasattr(os, "symlink"):
    SL = W / "sl_src"; DL = W / "sl_dst"
    (SL / "sub").mkdir(parents=True); (DL / "sub").mkdir(parents=True)
    (SL / "a.txt").write_text("a", encoding="utf-8")
    os.symlink("a.txt", SL / "link.txt"); os.symlink("missing", SL / "dangling"); os.symlink("sub", SL / "dirlink")
    (DL / "link.txt").write_text("real file", encoding="utf-8"); (DL / "dirlink").mkdir()
    upd._sync_dir(SL, DL)
    assert os.readlink(DL / "link.txt") == "a.txt" and os.readlink(DL / "dangling") == "missing"
    assert os.readlink(DL / "dirlink") == "sub" and (DL / "a.txt").read_text(encoding="utf-8") == "a"
    upd._sync_dir(SL, DL)   # idempotent
    assert os.readlink(DL / "dirlink") == "sub"
    OUT = W / "sl_outside"; OUT.mkdir()
    shutil.rmtree(DL / "sub"); os.symlink(str(OUT), DL / "sub")   # a real folder in the backup is a link now
    (SL / "sub" / "f.txt").write_text("f", encoding="utf-8")
    upd._sync_dir(SL, DL)
    assert not (DL / "sub").is_symlink() and (DL / "sub" / "f.txt").is_file() and not list(OUT.iterdir())
    print("symlinks: OK")

print("test_update: all checks passed")
