#!/usr/bin/env python3
"""Tests for tools/diff_inventory.py.

Usage:  python3 -I tests/test_diff_inventory.py

Builds a fake home (CUSTOMIZATION_AUDIT_HOME) and a copy of the overview page in a temporary folder,
fills the page with data of the fake inventory (tools/import_data.py), changes the fake home and
checks exit codes and output. Scenarios: no change, plugin added, removed, disabled, token change
(also below the threshold), empty page, empty page with empty home. Standard library only.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent
TOOLS = ROOT / "tools"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def add_plugin(home, name, descr, enabled=True):
    p = home / ".claude" / "plugins" / "cache" / "mk" / name / "1.0"
    write(p / "skills" / "s" / "SKILL.md", "---\nname: s\ndescription: %s\n---\nbody\n" % descr)
    f = home / ".claude" / "plugins" / "installed_plugins.json"
    data = json.loads(f.read_text()) if f.exists() else {"version": 2, "plugins": {}}
    data["plugins"][name + "@mk"] = [{"installPath": str(p)}]
    write(f, json.dumps(data))
    s = home / ".claude" / "settings.json"
    sd = json.loads(s.read_text()) if s.exists() else {"enabledPlugins": {}}
    sd["enabledPlugins"][name + "@mk"] = enabled
    write(s, json.dumps(sd))


def remove_plugin(home, name):
    f = home / ".claude" / "plugins" / "installed_plugins.json"
    data = json.loads(f.read_text())
    del data["plugins"][name + "@mk"]
    write(f, json.dumps(data))


def make_home(root):
    home = Path(root) / "home"
    add_plugin(home, "alpha", "A" * 740)    # ~200 tokens
    add_plugin(home, "beta", "B" * 370)
    add_plugin(home, "gamma", "C" * 370)
    write(home / ".claude" / "skills" / "my-skill" / "SKILL.md",
          "---\nname: my-skill\ndescription: %s\n---\n" % ("D" * 370))
    return home


def run(args, home):
    env = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(home))
    p = subprocess.run([sys.executable, "-I", str(TOOLS / "diff_inventory.py")] + [str(a) for a in args],
                       env=env, capture_output=True, text=True)
    return p.returncode, p.stdout


def inventory_rows(home):
    env = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(home))
    out = subprocess.run([sys.executable, "-I", str(TOOLS / "inventory.py")], env=env,
                         capture_output=True, text=True, check=True).stdout
    lines = out.split("\n\n")[0].splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:]]


def fresh_page(tmp, name):
    d = Path(tmp) / name
    d.mkdir()
    shutil.copytree(ROOT / "assets", d / "assets")
    shutil.copy(ROOT / "audit-overview.html", d / "audit-overview.html")
    return d / "audit-overview.html"


def fill_page(tmp, home, name):
    """Page copy whose data matches the current fake inventory."""
    page = fresh_page(tmp, name)
    plugins = []
    for r in inventory_rows(home):
        if r["source"] in ("local-plugin", "own-skill"):
            plugins.append({"name": r["name"].split("@")[0], "source": "local" if r["source"] == "local-plugin" else "own-skill",
                            "status": "disabled" if r["status"] == "disabled" else "installed",
                            "tokens": "~%d" % round(int(r["description_chars"]) / 3.7)})
    data = {"meta": {"as_of": "2026-01-01"}, "plugins": plugins}
    j = Path(tmp) / (name + ".json")
    j.write_text(json.dumps(data), encoding="utf-8")
    p = subprocess.run([sys.executable, "-I", str(TOOLS / "import_data.py"), str(j), str(page)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return page


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        # no change
        home = make_home(tmp)
        page = fill_page(tmp, home, "p0")
        rc, out = run([page], home)
        check(rc == 0 and "No changes" in out, "no-change case: %d %s" % (rc, out))
        print("no change: OK")

        # added
        add_plugin(home, "delta", "E" * 370)
        rc, out = run([page], home)
        check(rc == 1 and "NEW" in out and "delta@mk" in out and "GONE" not in out, "added: %s" % out)
        print("added: OK")
        remove_plugin(home, "delta")

        # removed
        remove_plugin(home, "beta")
        rc, out = run([page], home)
        check(rc == 1 and "GONE" in out and "beta" in out and "NEW" not in out, "removed: %s" % out)
        print("removed: OK")
        add_plugin(home, "beta", "B" * 370)

        # disabled
        add_plugin(home, "gamma", "C" * 370, enabled=False)
        rc, out = run([page], home)
        check(rc == 1 and "STATUS DIFFERS" in out and "page says installed, now disabled" in out, "disabled: %s" % out)
        print("disabled: OK")
        add_plugin(home, "gamma", "C" * 370)

        # token change: alpha 200 -> 400 tokens (+100 %, +200); beta 100 -> 110 (below 50 tokens)
        add_plugin(home, "alpha", "A" * 1480)
        add_plugin(home, "beta", "B" * 407)
        rc, out = run([page], home)
        check(rc == 1 and "TOKEN ESTIMATE DIFFERS" in out and "alpha@mk: page ~200, now ~400" in out
              and "beta@mk" not in out, "tokens: %s" % out)
        rc, out = run([page, "--threshold", "150"], home)
        check(rc == 0, "threshold 150 should hide +100 %%: %s" % out)
        print("token change: OK")

        # inventory file instead of scan
        tsv = Path(tmp) / "inv.tsv"
        env = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=str(home))
        subprocess.run([sys.executable, "-I", str(TOOLS / "inventory.py"), str(tsv)], env=env,
                       capture_output=True, check=True)
        empty_home = Path(tmp) / "nothing"
        empty_home.mkdir()
        rc, out = run(["--inventory", tsv, page], empty_home)
        check(rc == 1 and "alpha@mk" in out, "--inventory: %s" % out)
        rc, out = run(["--inventory", Path(tmp) / "missing.tsv", page], home)
        check(rc == 2, "missing TSV must give exit 2")
        rc, out = run([Path(tmp) / "missing.html"], home)
        check(rc == 2, "missing page must give exit 2")
        print("inventory file and errors: OK")

        # empty page
        empty_page = fresh_page(tmp, "p1")
        rc, out = run([empty_page], home)
        check(rc == 1 and "no audit" in out and "alpha@mk" in out and "my-skill" in out, "empty page: %s" % out)
        rc, out = run([empty_page], empty_home)
        check(rc == 0, "empty page and empty home: %d %s" % (rc, out))
        print("empty page: OK")
    print("test_diff_inventory passed")


if __name__ == "__main__":
    main()
