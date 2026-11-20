#!/usr/bin/env python3
"""Loads or removes the fictional sample data in audit-overview.html.

Usage:  python3 -I tools/sample_data.py load   [path-to-html]
        python3 -I tools/sample_data.py remove [path-to-html]
        python3 -I tools/sample_data.py status [path-to-html]
        Default page: ../audit-overview.html (relative to this script).

load    writes the blocks of examples/sample-data.json into the page and runs tools/build_overview.py.
        Refuses (message, exit 1, page unchanged) if the page already holds real data, i.e. any
        non-empty data block while data-meta does not carry "sample": true.
remove  empties all data blocks (back to the empty state of a fresh checkout) and rebuilds.
        Refuses if the page holds real data (it only removes sample data).
status  prints whether sample data is loaded.

Standard library only.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "examples", "sample-data.json")
BUILDER = os.path.join(HERE, "build_overview.py")
BLOCKS = ["meta", "plugins", "claudeai-skills", "mcp", "builtin", "candidates", "overlaps", "open-items", "tokens"]
EMPTY = {"meta": {"as_of": None}, "plugins": [], "claudeai-skills": [], "mcp": [], "builtin": [], "candidates": [],
         "overlaps": {"measured_on": None, "fields": []}, "open-items": [], "tokens": None}


def pattern(name):
    return re.compile(r'(<script type="application/json" id="data-%s">)(.*?)(</script>)' % re.escape(name), re.S)


def read_blocks(html):
    out = {}
    for name in BLOCKS:
        m = pattern(name).search(html)
        if not m:
            raise SystemExit("ERROR: JSON block #data-%s not found in the page." % name)
        try:
            out[name] = json.loads(m.group(2))
        except ValueError as e:
            raise SystemExit("ERROR: JSON block #data-%s is not valid JSON: %s" % (name, e))
    return out


def is_sample(blocks):
    meta = blocks["meta"]
    return isinstance(meta, dict) and meta.get("sample") is True


def has_real_data(blocks):
    if is_sample(blocks):
        return False
    return any(blocks[n] != EMPTY[n] for n in BLOCKS)


def write_blocks(html, values):
    for name in BLOCKS:
        text = json.dumps(values[name], ensure_ascii=False).replace("</", "<\\/")
        html = pattern(name).sub(lambda m: m.group(1) + text + m.group(3), html, count=1)
    return html


def build(path):
    return subprocess.call([sys.executable, "-I", BUILDER, path])


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("load", "remove", "status") or len(args) > 2:
        print(__doc__)
        return 2
    cmd = args[0]
    path = os.path.abspath(args[1] if len(args) > 1 else os.path.join(HERE, "..", "audit-overview.html"))
    with open(path, encoding="utf-8", newline="") as f:
        html = f.read()
    blocks = read_blocks(html)
    if cmd == "status":
        print("sample data is loaded" if is_sample(blocks) else "no sample data loaded")
        return 0
    if has_real_data(blocks):
        print("ERROR: the page already holds real data (non-empty blocks without \"sample\": true). "
              "Nothing was changed.")
        return 1
    if cmd == "load":
        with open(SAMPLE, encoding="utf-8") as f:
            sample = json.load(f)
        if not isinstance(sample, dict) or not isinstance(sample.get("meta"), dict) or sample["meta"].get("sample") is not True:
            print("ERROR: examples/sample-data.json must carry meta.sample = true. Nothing was changed.")
            return 1
        values = {n: sample[n] for n in BLOCKS}
    else:
        values = EMPTY
    new = write_blocks(html, values)
    if new != html:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    rc = build(path)
    if rc != 0:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(html)
        print("ERROR: the build failed; the page was restored.")
        return 1
    print("sample data loaded" if cmd == "load" else "sample data removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
