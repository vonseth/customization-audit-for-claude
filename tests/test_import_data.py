"""Tests for tools/import_data.py. Run: python3 -I tests/test_import_data.py
Works on copies of the page in a temp dir; the real page is never touched."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
TOOL = str(ROOT / "tools" / "import_data.py")
TMP = tempfile.TemporaryDirectory()
W = Path(TMP.name).resolve()
shutil.copytree(ROOT / "assets", W / "assets")
PAGE = W / "audit-overview.html"
shutil.copyfile(ROOT / "audit-overview.html", PAGE)
(W / "nothing.json").write_text("{}", encoding="utf-8")


def run(*args):
    p = subprocess.run([sys.executable, "-I", TOOL] + [str(a) for a in args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


# (d) -h / --help: usage on stdout, exit 0, nothing read (the file does not exist)
for a in (["-h"], ["--help"], ["missing.json", "--help"], ["--export", "x.json", "-h"]):
    rc, out, err = run(*a)
    assert rc == 0 and "Usage:" in out and err == "", (a, rc, err)
rc, out, err = run()
assert rc == 2 and out == "" and "Usage:" in err
assert run("--force", W / "nothing.json", PAGE)[0] == 2  # --force belongs to --export

# an empty page for the tests below
assert run(W / "nothing.json", "--replace", PAGE)[0] == 0

# (a) page without its assets/ folder: clear error, no traceback
lone = W / "lone"
lone.mkdir()
shutil.copyfile(PAGE, lone / "audit-overview.html")
rc, out, err = run(W / "nothing.json", "--replace", lone / "audit-overview.html")
assert rc == 1 and "assets" in err and "Traceback" not in err and out == "", (rc, out, err)
rc, out, err = run(W / "nothing.json", "--replace", lone / "no-such-page.html")
assert rc == 1 and "not found" in err and "Traceback" not in err, err

# (b) --export never overwrites silently
dest = W / "export.json"
assert run("--export", dest, PAGE)[0] == 0 and dest.exists()
dest.write_text("precious", encoding="utf-8")
rc, out, err = run("--export", dest, PAGE)
assert rc == 1 and "already exists" in err and "--force" in err and dest.read_text(encoding="utf-8") == "precious"
rc, out, err = run("--export", dest, "--force", PAGE)
assert rc == 0 and json.loads(dest.read_text(encoding="utf-8"))["meta"], (rc, err)
# ... and never the page itself, not even with --force: same path, a symlink, another spelling of the name
before = PAGE.read_bytes()
link = W / "link.json"
link.symlink_to(PAGE)
for target in (PAGE, link, W / "assets" / ".." / "audit-overview.html"):
    for extra in ([], ["--force"]):
        rc, out, err = run("--export", target, *extra, PAGE)
        assert rc == 1 and "page itself" in err and PAGE.read_bytes() == before, (target, extra, rc, err)
swapped = W / "AUDIT-OVERVIEW.HTML"
if swapped.exists():  # case-insensitive file system
    rc, out, err = run("--export", swapped, "--force", PAGE)
    assert rc == 1 and "page itself" in err and PAGE.read_bytes() == before

# (c) bad data: clear message and exit 1, never a traceback
bad = W / "bad.json"
bad.write_text("{not json", encoding="utf-8")
rc, out, err = run(bad, "--replace", PAGE)
assert rc == 1 and "ERROR" in err and "Traceback" not in err
bad.write_text("[1, 2]", encoding="utf-8")
rc, out, err = run(bad, "--replace", PAGE)
assert rc == 1 and "JSON object" in err and "Traceback" not in err
bad.write_text(json.dumps({"meta": {"schema_version": 999}}), encoding="utf-8")
rc, out, err = run(bad, "--replace", PAGE)
assert rc == 1 and "newer version" in err and "Traceback" not in err
# a ValueError from the page itself (newer schema in the page) used to end in a traceback on --export
newer = W / "newer.html"
t = PAGE.read_text(encoding="utf-8")
m = re.search(r'(id="data-meta">)(.*?)(</script>)', t, re.S)
newer.write_text(t[:m.start(2)] + '{"schema_version": 999}' + t[m.end(2):], encoding="utf-8")
rc, out, err = run("--export", W / "newer-export.json", newer)
assert rc == 1 and "newer version" in err and "Traceback" not in err and not (W / "newer-export.json").exists(), (rc, err)

print("test_import_data: OK")
