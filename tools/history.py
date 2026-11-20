#!/usr/bin/env python3
"""Keeps the history of your audits (the data-history block of audit-overview.html).

Usage:  python3 -I tools/history.py snapshot [--date YYYY-MM-DD] [--note TEXT] [--replace] [path-to-html]
        python3 -I tools/history.py list [path-to-html]
        Default page: ../audit-overview.html (relative to this script).

snapshot  Appends the current numbers of the page as one snapshot and rebuilds the page:
            tokens      = data-tokens "now"
            installed   = plugins and own skills that are not removed (like the first key figure card)
            removed     = plugins and own skills with status removed (like the "removed" key figure card)
            candidates  = candidates still listed as not installed
          --date defaults to today. A second snapshot with the same date is refused unless --replace is
          given (then the existing one is overwritten). A date before the latest snapshot is refused.
          Run it after the numbers of the page are final, e.g. at the end of an audit.
          With two or more snapshots the token card shows a "History" timeline.
list      Prints the snapshots as a table.

-h, --help (anywhere in the arguments) prints this help and exits 0.

If the build fails, the page is restored. Standard library only.
"""
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(HERE, "build_overview.py")
PATTERN = re.compile(r'(<script type="application/json" id="data-history">)(.*?)(</script>)', re.S)

spec = importlib.util.spec_from_file_location("build_overview", BUILDER)
bo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bo)


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def raw_history(html):
    m = PATTERN.search(html)
    if not m:
        raise SystemExit("ERROR: JSON block #data-history not found in the page (page from an older version?).")
    try:
        value = json.loads(m.group(2))
    except ValueError as e:
        raise SystemExit("ERROR: JSON block #data-history is not valid JSON: %s" % e)
    if not isinstance(value, list):
        raise SystemExit("ERROR: JSON block #data-history must be a list.")
    return value


def current_numbers(html):
    try:
        data = bo.load_all(html)
    except bo.Fail as e:
        raise SystemExit("ERROR: %s" % e)
    if not data["tokens"]:
        raise SystemExit("ERROR: the page has no measured tokens (data-tokens is empty). Nothing was changed.")
    pl = data["plugins"]
    return {"tokens": data["tokens"]["now"],
            "installed": sum(1 for r in pl if r["status"] != "removed"),
            "removed": sum(1 for r in pl if r["status"] == "removed"),
            "candidates": sum(1 for r in data["candidates"] if r["removal_reason"].empty())}


def snapshot(path, date, note, replace):
    html = read(path)
    hist = raw_history(html)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        print("ERROR: --date must look like YYYY-MM-DD.", file=sys.stderr)
        return 1
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        print("ERROR: %s is not a valid date." % date, file=sys.stderr)
        return 1
    dates = [h.get("date") for h in hist if isinstance(h, dict)]
    if date in dates and not replace:
        print("ERROR: a snapshot for %s already exists. Use --replace to overwrite it, or --date for another day. "
              "Nothing was changed." % date, file=sys.stderr)
        return 1
    rest = [h for h in hist if not (isinstance(h, dict) and h.get("date") == date)]
    if rest and date < max(h.get("date", "") for h in rest):
        print("ERROR: %s is before the latest snapshot (%s). Nothing was changed." % (date, max(h.get("date", "") for h in rest)), file=sys.stderr)
        return 1
    snap = {"date": date}
    snap.update(current_numbers(html))
    if note:
        snap["note"] = note
    new_hist = rest + [snap]
    text = json.dumps(new_hist, ensure_ascii=False).replace("</", "<\\/")
    write(path, PATTERN.sub(lambda m: m.group(1) + text + m.group(3), html, count=1))
    res = subprocess.run([sys.executable, "-I", BUILDER, path], capture_output=True, text=True)
    if res.returncode != 0:
        write(path, html)
        print("ERROR: the build failed; the page was restored.\n" + res.stdout.strip() + res.stderr.strip(), file=sys.stderr)
        return 1
    print("Snapshot %s: %d tokens, %d installed, %d removed, %d candidates (%d snapshot%s in total)"
          % (date, snap["tokens"], snap["installed"], snap["removed"], snap["candidates"], len(new_hist),
             "" if len(new_hist) == 1 else "s"))
    return 0


def listing(path):
    hist = raw_history(read(path))
    if not hist:
        print("No snapshots yet. Create one with: python3 -I tools/history.py snapshot")
        return 0
    print("%-12s %8s %10s %8s %11s  %s" % ("date", "tokens", "installed", "removed", "candidates", "note"))
    for h in hist:
        note = h.get("note", "")
        if isinstance(note, dict):
            note = note.get("en") or note.get("de") or ""
        print("%-12s %8s %10s %8s %11s  %s" % (h.get("date"), h.get("tokens"), h.get("installed"), h.get("removed"),
                                              h.get("candidates"), note))
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return 0
    if not args or args[0] not in ("snapshot", "list"):
        print(__doc__, file=sys.stderr)
        return 2
    cmd, rest = args[0], args[1:]
    date, note, replace, pos = datetime.date.today().isoformat(), "", False, []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--replace":
            replace = True
        elif a in ("--date", "--note") and cmd == "snapshot":
            if i + 1 >= len(rest):
                print("ERROR: %s needs a value." % a, file=sys.stderr)
                return 2
            if a == "--date":
                date = rest[i + 1]
            else:
                note = rest[i + 1]
            i += 1
        elif a.startswith("--") or (a == "--replace" and cmd == "list"):
            print(__doc__, file=sys.stderr)
            return 2
        else:
            pos.append(a)
        i += 1
    if len(pos) > 1 or (cmd == "list" and replace):
        print(__doc__, file=sys.stderr)
        return 2
    path = os.path.abspath(pos[0] if pos else os.path.join(HERE, "..", "audit-overview.html"))
    if not os.path.isfile(path):
        print("ERROR: %s not found." % path, file=sys.stderr)
        return 1
    return snapshot(path, date, note, replace) if cmd == "snapshot" else listing(path)


if __name__ == "__main__":
    sys.exit(main())
