#!/usr/bin/env python3
"""Moves audit data into audit-overview.html, or writes the data of the page out to a file.

Usage:  python3 -I tools/import_data.py <file.json> [--replace] [path-to-html]
        python3 -I tools/import_data.py --export <file.json> [path-to-html]
        Default page: ../audit-overview.html (relative to this script).

import   Reads <file.json> (same shape as examples/sample-data.json: the ten blocks meta, plugins,
         claudeai-skills, mcp, builtin, candidates, overlaps, open-items, tokens, history; a missing block is
         treated as empty, unknown keys are errors). First writes the blocks into a temporary copy of the
         page and builds it there; any schema error is reported and nothing is touched. Then writes the
         blocks into the page and runs tools/build_overview.py. Refuses (page unchanged) if the page
         already holds data, sample or real, unless --replace is given. <file.json> is never modified.
--export Writes the current data blocks of the page to <file.json> in the same format (backup, or moving
         your data to a newer download of the project). Refuses to overwrite the page itself.

Standard library only.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(HERE, "build_overview.py")


def load_sample_tools():
    """Reuses the block helpers of tools/sample_data.py (isolated mode has no import path to this folder)."""
    spec = importlib.util.spec_from_file_location("sample_data", os.path.join(HERE, "sample_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SD = load_sample_tools()
BLOCKS = SD.BLOCKS
EMPTY = SD.EMPTY


def read_page(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def holds_data(blocks):
    if SD.is_sample(blocks):
        return True
    for n in BLOCKS:
        if n == "meta":
            meta = blocks[n]
            if isinstance(meta, dict) and (meta.get("as_of") or meta.get("sample")):
                return True
        elif blocks[n] != EMPTY[n]:
            return True
    return False


def load_input(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise SystemExit("ERROR: cannot read %s: %s" % (path, e))
    if not isinstance(raw, dict):
        raise SystemExit("ERROR: %s must hold a JSON object with the blocks %s." % (path, ", ".join(BLOCKS)))
    unknown = [k for k in raw if k not in BLOCKS]
    if unknown:
        raise SystemExit("ERROR: unknown key(s) in %s: %s (allowed: %s)" % (path, ", ".join(unknown), ", ".join(BLOCKS)))
    return {n: raw.get(n, EMPTY[n]) for n in BLOCKS}


def build(path):
    return subprocess.run([sys.executable, "-I", BUILDER, path], capture_output=True, text=True)


def validate(page_path, html, values):
    """Builds the new data into a temporary copy of the page (with its assets); returns the builder result."""
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(os.path.join(os.path.dirname(page_path), "assets"), os.path.join(tmp, "assets"))
        copy = os.path.join(tmp, "audit-overview.html")
        with open(copy, "w", encoding="utf-8", newline="") as f:
            f.write(SD.write_blocks(html, values))
        return build(copy)


def counts(values):
    pl, sk, mc, ca, ov = values["plugins"], values["claudeai-skills"], values["mcp"], values["candidates"], values["overlaps"]
    return [
        ("plugins and own skills", len(pl), "%d installed, %d disabled, %d removed" % (
            sum(1 for r in pl if r.get("status") == "installed"), sum(1 for r in pl if r.get("status") == "disabled"),
            sum(1 for r in pl if r.get("status") == "removed"))),
        ("claude.ai skills", len(sk), "%d active, %d removed" % (
            sum(1 for r in sk if r.get("status") == "active"), sum(1 for r in sk if r.get("status") == "removed"))),
        ("MCP servers", len(mc), "%d connected, %d not signed in, %d removed" % (
            sum(1 for r in mc if r.get("status") == "connected"), sum(1 for r in mc if r.get("status") == "not_signed_in"),
            sum(1 for r in mc if r.get("status") == "removed"))),
        ("built-in", len(values["builtin"]), ""),
        ("candidates", len(ca), "%d still listed, %d in the removed archive" % (
            sum(1 for r in ca if not r.get("removal_reason")), sum(1 for r in ca if r.get("removal_reason")))),
        ("overlap topics", len(ov.get("fields", [])), "%d members" % sum(len(f.get("members", [])) for f in ov.get("fields", []))),
        ("open items", len(values["open-items"]), ""),
        ("tokens", 1 if values["tokens"] else 0, ""),
        ("history snapshots", len(values["history"]), ""),
    ]


def do_import(src, page, replace):
    html = read_page(page)
    blocks = SD.read_blocks(html)
    if holds_data(blocks) and not replace:
        print("ERROR: the page already holds data (sample or your own). Nothing was changed.\n"
              "Use --replace to overwrite it. Tip: save the current data first with\n"
              "  python3 -I tools/import_data.py --export backup.json")
        return 1
    values = load_input(src)
    res = validate(page, html, values)
    if res.returncode != 0:
        print("ERROR: the data does not fit the schema; nothing was changed.\n" + res.stdout.strip() + res.stderr.strip())
        return 1
    new = SD.write_blocks(html, values)
    with open(page, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    res = build(page)
    if res.returncode != 0:
        with open(page, "w", encoding="utf-8", newline="") as f:
            f.write(html)
        print("ERROR: the build failed; the page was restored.\n" + res.stdout.strip() + res.stderr.strip())
        return 1
    print("Imported %s into %s" % (src, page))
    for label, n, extra in counts(values):
        print("  %-24s %3d  %s" % (label, n, extra))
    if values["meta"].get("sample"):
        print("Note: meta.sample is true, so the page shows the sample notice.")
    print("As of: %s" % (values["meta"].get("as_of") or "-"))
    print("Next steps:\n  python3 -I tools/check_overview.py      # check the page\n"
          "  open audit-overview.html in your browser\n"
          "  keep the JSON file as your backup; it is not modified")
    return 0


def do_export(dest, page):
    if os.path.abspath(dest) == os.path.abspath(page):
        print("ERROR: the export file must not be the page itself.")
        return 1
    blocks = SD.read_blocks(read_page(page))
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(blocks, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("Exported the data of %s to %s" % (page, dest))
    for label, n, extra in counts(blocks):
        print("  %-24s %3d  %s" % (label, n, extra))
    return 0


def main():
    args = sys.argv[1:]
    replace = "--replace" in args
    export = "--export" in args
    rest = [a for a in args if a not in ("--replace", "--export")]
    if not rest or len(rest) > 2 or any(a.startswith("--") for a in rest) or (export and replace):
        print(__doc__)
        return 2
    page = os.path.abspath(rest[1] if len(rest) > 1 else os.path.join(HERE, "..", "audit-overview.html"))
    if export:
        return do_export(rest[0], page)
    return do_import(rest[0], page, replace)


if __name__ == "__main__":
    sys.exit(main())
