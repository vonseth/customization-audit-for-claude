"""Tests for tools/history.py and the history timeline. Run: python3 -I tests/test_history.py
Works on a copy of the page in a temp dir; the real page is never touched."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
PY = [sys.executable, "-I"]
TMP = tempfile.TemporaryDirectory()
W = Path(TMP.name).resolve()
shutil.copytree(ROOT / "assets", W / "assets")
# an empty page, independent of whatever data the real page holds
EMPTY_PAGE = W / "empty-template.html"
shutil.copyfile(ROOT / "audit-overview.html", EMPTY_PAGE)
(W / "nothing.json").write_text("{}", encoding="utf-8")
assert subprocess.run(PY + [str(ROOT / "tools" / "import_data.py"), str(W / "nothing.json"), "--replace", str(EMPTY_PAGE)],
                      capture_output=True).returncode == 0


def run(script, *args):
    p = subprocess.run(PY + [str(ROOT / "tools" / script)] + [str(a) for a in args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def fresh(name):
    page = W / name
    shutil.copyfile(EMPTY_PAGE, page)
    assert run("sample_data.py", "load", page)[0] == 0
    return page


def history_block(page):
    m = re.search(r'id="data-history">(.*?)</script>', page.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1))


def rows(page):
    t = page.read_text(encoding="utf-8")
    return len(re.findall(r'<li class="hist-row', t)), 'class="history"' in t


# sample data ships with 4 snapshots -> timeline with 4 rows, check passes
page = fresh("a.html")
assert len(history_block(page)) == 4
assert rows(page) == (4, True)
rc, out = run("check_overview.py", page)
assert "PASS 12  history (4 snapshots)" in out and "FAIL" not in out, out

# list
rc, out = run("history.py", "list", page)
assert rc == 0 and "2026-01-15" in out and "4200" in out, out

# snapshot: new date appended with the numbers of the page (19 installed, 2 removed, 5 candidates, 4200 tokens)
rc, out = run("history.py", "snapshot", "--date", "2026-02-01", "--note", "test note", page)
assert rc == 0, out
h = history_block(page)
assert len(h) == 5 and h[-1] == {"date": "2026-02-01", "tokens": 4200, "installed": 19, "removed": 2,
                                  "candidates": 5, "note": "test note"}, h[-1]
assert rows(page) == (5, True)
assert "test note" in page.read_text(encoding="utf-8")

# duplicate date refused, page unchanged
before = page.read_bytes()
rc, out = run("history.py", "snapshot", "--date", "2026-02-01", page)
assert rc == 1 and "already exists" in out and page.read_bytes() == before, out

# --replace overwrites (note disappears because none is given)
rc, out = run("history.py", "snapshot", "--date", "2026-02-01", "--replace", page)
assert rc == 0, out
h = history_block(page)
assert len(h) == 5 and "note" not in h[-1], h[-1]

# date before the latest snapshot refused; invalid date refused
assert run("history.py", "snapshot", "--date", "2025-01-01", page)[0] == 1
assert run("history.py", "snapshot", "--date", "2026-13-01", page)[0] == 1
assert page.read_bytes() != before  # replaced above, but still valid
assert run("check_overview.py", page)[0] == 0

# rendering with 1 snapshot: nothing shown; with 0: nothing
one = fresh("b.html")
txt = one.read_text(encoding="utf-8")
m = re.search(r'(id="data-history">)(.*?)(</script>)', txt, re.S)
first = json.loads(m.group(2))[:1]
one.write_text(txt[:m.start(2)] + json.dumps(first) + txt[m.end(2):], encoding="utf-8")
assert run("build_overview.py", one)[0] == 0
assert rows(one) == (0, False)
assert run("check_overview.py", one)[0] == 0
one.write_text(one.read_text(encoding="utf-8").replace(json.dumps(first), "[]"), encoding="utf-8")
assert run("build_overview.py", one)[0] == 0 and rows(one) == (0, False)

# validation: unsorted dates, duplicate dates, unknown key, missing key
bad = fresh("c.html")
txt = bad.read_text(encoding="utf-8")
m = re.search(r'(id="data-history">)(.*?)(</script>)', txt, re.S)
base = json.loads(m.group(2))
for broken, why in ((base[::-1], "sorted"), (base + [base[-1]], "unique"),
                    ([dict(base[0], extra=1)] + base[1:], "unknown key"),
                    ([{k: v for k, v in base[0].items() if k != "tokens"}] + base[1:], "required")):
    bad.write_text(txt[:m.start(2)] + json.dumps(broken) + txt[m.end(2):], encoding="utf-8")
    rc, out = run("build_overview.py", bad)
    assert rc == 1 and "data-history" in out, (why, out)

# a snapshot needs measured tokens: the empty page refuses
empty = W / "empty.html"
shutil.copyfile(EMPTY_PAGE, empty)
rc, out = run("history.py", "snapshot", empty)
assert rc == 1 and "no measured tokens" in out, out

# export / import round trip keeps the history
page = fresh("d.html")
exp = W / "export.json"
assert run("import_data.py", "--export", exp, page)[0] == 0
assert len(json.loads(exp.read_text(encoding="utf-8"))["history"]) == 4
other = W / "e.html"
shutil.copyfile(EMPTY_PAGE, other)
rc, out = run("import_data.py", exp, other)
assert rc == 0, out
assert history_block(other) == history_block(page) and rows(other) == (4, True)
# a file without the history block imports as empty history
d = json.loads(exp.read_text(encoding="utf-8"))
del d["history"]
exp2 = W / "export2.json"
exp2.write_text(json.dumps(d), encoding="utf-8")
assert run("import_data.py", exp2, "--replace", other)[0] == 0 and history_block(other) == []

# remove sample data empties the history again
page = fresh("f.html")
assert run("sample_data.py", "remove", page)[0] == 0 and history_block(page) == []
# help anywhere prints help and exits 0
for args in (["-h"], ["--help"], ["snapshot", "--help"], ["snapshot", "-h"], ["list", "--help"]):
    rc, out = run("history.py", *args)
    assert rc == 0 and "snapshot" in out and "Usage" in out, (args, rc)

# snapshot works when an existing history entry has no "date"
page = fresh("g.html")
t = page.read_text(encoding="utf-8")
t = re.sub(r'(id="data-history">)(.*?)(</script>)', lambda m: m.group(1) + '[{"tokens": 1}]' + m.group(3), t, flags=re.S)
page.write_text(t, encoding="utf-8")
rc, out = run("history.py", "snapshot", "--date", "2026-01-01", page)
assert "Traceback" not in out and "KeyError" not in out, out
print("test_history: all checks passed")
