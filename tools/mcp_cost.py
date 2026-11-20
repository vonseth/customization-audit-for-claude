#!/usr/bin/env python3
"""Measures the context cost of MCP servers from the output of Claude Code's /context command.

IMPORTANT: the USER runs /context in Claude Code (desktop app or CLI) and pastes or saves the output.
Claude never runs /context itself, and this script never starts Claude or touches ~/.claude.

Usage:  python3 -I tools/mcp_cost.py <file | -> [--write [page]] [--date YYYY-MM-DD]
        "-" reads the text from stdin (paste, then Ctrl-D). Put the input file BEFORE --write
        (--write takes the next argument as the page). Default page: ../audit-overview.html.

Input (both formats are understood, mixed spacing, separators and languages are tolerated):
  (a) Desktop app, copied text. Summary lines "MCP tools 18.442 1,8 %", "MCP server instructions 4.136 0,4 %",
      "MCP tools (deferred) 132.468 -" and a section "MCP-Tools 150.910 253" (German label; the third column is a
      plain count) followed by one line per tool: "Linear · Create attachment (deprecated) 1.345"
      (server · tool name, tokens). Lines of other sections (memory files, agents, skills, messages, system
      tools ...) are ignored; the tool section ends at the next heading with a number.
  (b) CLI text: "MCP tools: 18.4k tokens (1.8%)", "MCP tools (deferred): ..." and tool lines
      "mcp__linear__create_issue (linear): 1,345 tokens" or "mcp__server__tool: 1.3k tokens".
  Numbers: thousands separators ".", ",", apostrophe or (narrow) no-break space, or none; with the suffix k the
  last "." or "," is the decimal mark (18.4k = 18,400). Percent columns, "tokens", the dash column and leading
  symbols or box characters are ignored.

Output (stdout):
  permanent MCP cost per session = loaded MCP tools + MCP server instructions (measured),
  deferred total (loaded only on demand), and a table per server: number of tools and the total tokens of
  ALL its tools, sorted by tokens. The per-server totals cannot be split into loaded and deferred: /context
  lists every tool of a server with its own size, but not which tools are loaded.
  Exit 1 with a message if the text holds no MCP lines at all.

--write [page]  (1) sets data-tokens "mcp" = {"permanent", "deferred", "measured_on"} (--date, default today);
                (2) sets "context_tokens" (all tools of the server) on every data-mcp entry whose name matches a
                server: case-insensitive, spaces, hyphens and underscores ignored; the part before " (" is tried
                too. Then builds the page; if the build fails the page is restored. Needs a measured data-tokens
                block (data-tokens is null on an empty page: set "now" first). Unmatched servers are listed;
                entries that were not measured keep their old value.
Standard library only.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(HERE, "build_overview.py")
DEFAULT_PAGE = os.path.join(HERE, "..", "audit-overview.html")

SEP = "[.,'’  ]"
NUM = r"(\d+(?:%s\d+)*)([kK])?" % SEP
DOT = "[·•∙]"
PERCENT_TAIL = re.compile(r"\s*\(?\s*\d+(?:[.,]\d+)?\s*%\s*\)?\s*$")
DASH_TAIL = re.compile(r"\s+[—–-]\s*$")
TOKENS_TAIL = re.compile(r"\s+tokens?\s*$", re.I)
DEFER_WORDS = ("defer", "zurückgestellt", "zurueckgestellt", "aufgesch", "verzöger", "nachgeladen", "bedarf",
               "demand", "lazy")

SUMMARY = re.compile(r"^(mcp[\s-]*tools?|mcp[\s-]*server[\s-]*(?:instructions?|anweisungen))\s*(?:\(([^)]*)\))?\s*:?\s+%s(?:\s+(\d+))?$"
                     % NUM, re.I)
DESKTOP_TOOL = re.compile(r"^(.+?)\s+%s\s+(.+?)\s+%s$" % (DOT, NUM))
CLI_TOOL = re.compile(r"^(mcp__.+?)\s*(?:\(([^)]*)\))?\s*:\s*%s$" % NUM, re.I)
GENERIC = re.compile(r"^[^\d].*?\s%s(?:\s+\S+)?$" % NUM)


def to_int(digits, k):
    if k:
        t = digits.replace(",", ".")
        parts = re.split(r"[.'’  ]", t)
        t = "".join(parts[:-1]) + "." + parts[-1] if len(parts) > 1 else t
        return int(round(float(t) * 1000))
    return int(re.sub(r"\D", "", digits))


def clean(line):
    s = re.sub(r"^[^\w]+", "", line.strip())
    s = PERCENT_TAIL.sub("", s)
    s = DASH_TAIL.sub("", s)
    s = TOKENS_TAIL.sub("", s)
    return PERCENT_TAIL.sub("", s).strip()


def parse(text):
    """Returns dict: loaded, instructions, deferred (int|None), tools: [(server, tool, tokens)], notes [str]."""
    res = {"loaded": None, "instructions": None, "deferred": None, "tools": [], "notes": []}
    in_section, header_total, header_count = False, None, None
    for raw in text.splitlines():
        s = clean(raw)
        if not s:
            continue
        m = SUMMARY.match(s)
        if m:
            label, paren, digits, k, count = m.group(1).lower(), m.group(2), m.group(3), m.group(4), m.group(5)
            value = to_int(digits, k)
            if "instr" in label or "anweis" in label:
                res["instructions"] = value
                in_section = False
            elif paren and any(w in paren.lower() for w in DEFER_WORDS):
                res["deferred"] = value
                in_section = False
            elif count is not None and not paren and not k:
                in_section, header_total, header_count = True, value, int(count)
            else:
                res["loaded"] = value
                in_section = False
            continue
        m = CLI_TOOL.match(s)
        if m:
            server = m.group(2) or (m.group(1)[5:].split("__", 1)[0])
            res["tools"].append((server.strip(), m.group(1), to_int(m.group(3), m.group(4))))
            continue
        m = DESKTOP_TOOL.match(s)
        if m and in_section:
            res["tools"].append((m.group(1).strip(), m.group(2).strip(), to_int(m.group(3), m.group(4))))
            continue
        if in_section and GENERIC.match(s) and not re.search(r"\s%s\s" % DOT, s):
            in_section = False  # next section heading
    if header_total is not None:
        got = sum(t for _, _, t in res["tools"])
        if res["tools"] and (got != header_total or len(res["tools"]) != header_count):
            res["notes"].append("section header says %d tokens in %d tools, the tool lines add up to %d tokens in %d tools"
                                % (header_total, header_count, got, len(res["tools"])))
    return res


def servers(tools):
    acc = {}
    for server, _, tokens in tools:
        n, t = acc.get(server, (0, 0))
        acc[server] = (n + 1, t + tokens)
    return sorted(((s, n, t) for s, (n, t) in acc.items()), key=lambda x: (-x[2], x[0].lower()))


def permanent(res):
    if res["loaded"] is None and res["instructions"] is None:
        return None
    return (res["loaded"] or 0) + (res["instructions"] or 0)


def report(res):
    perm = permanent(res)
    out = ["MCP context cost (measured with /context)", ""]
    if perm is None:
        out.append("Permanent MCP cost per session:  not found (no summary lines 'MCP tools' / 'MCP server instructions')")
    else:
        out.append("Permanent MCP cost per session:  %s tokens" % format(perm, ",d"))
        out.append("  loaded MCP tools:              %s" % ("%s" % format(res["loaded"], ",d") if res["loaded"] is not None else "not found"))
        out.append("  MCP server instructions:       %s" % ("%s" % format(res["instructions"], ",d") if res["instructions"] is not None else "not found"))
    out.append("Deferred (loaded only on demand): %s" % (format(res["deferred"], ",d") + " tokens" if res["deferred"] is not None else "not found"))
    rows = servers(res["tools"])
    if rows:
        out += ["", "Per server: number of tools and tokens of ALL its tools. Loaded and deferred tools cannot be",
                "told apart in this list, so the per-server totals cannot be split into loaded and deferred.", ""]
        w = max(len(r[0]) for r in rows + [("server", 0, 0)])
        out.append("%-*s  %6s  %10s" % (w, "server", "tools", "tokens"))
        for s, n, t in rows:
            out.append("%-*s  %6d  %10s" % (w, s, n, format(t, ",d")))
        out.append("%-*s  %6d  %10s" % (w, "total", sum(r[1] for r in rows), format(sum(r[2] for r in rows), ",d")))
    for n in res["notes"]:
        out.append("Note: " + n)
    return "\n".join(out)


def norm(name):
    return re.sub(r"[\s_-]+", "", name).lower()


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def block_pattern(name):
    return re.compile(r'(<script type="application/json" id="data-%s">)(.*?)(</script>)' % re.escape(name), re.S)


def dump(v):
    return json.dumps(v, ensure_ascii=False).replace("</", "<\\/")


def write_page(path, res, date):
    html = read(path)
    blocks = {}
    for n in ("tokens", "mcp"):
        m = block_pattern(n).search(html)
        if not m:
            print("ERROR: JSON block #data-%s not found in the page. Nothing was changed." % n)
            return 1
        try:
            blocks[n] = json.loads(m.group(2))
        except ValueError as e:
            print("ERROR: JSON block #data-%s is not valid JSON: %s. Nothing was changed." % (n, e))
            return 1
    if not isinstance(blocks["tokens"], dict) or not isinstance(blocks["mcp"], list):
        print("ERROR: data-tokens is empty (null). Measure the permanent tokens first (tools/inventory.py, then set "
              "data-tokens \"now\"); nothing was changed.")
        return 1
    perm = permanent(res)
    if perm is None:
        print("ERROR: no summary lines ('MCP tools', 'MCP server instructions') in the input, so data-tokens \"mcp\" "
              "cannot be set. Nothing was changed.")
        return 1
    blocks["tokens"]["mcp"] = {"permanent": perm, "deferred": res["deferred"] or 0, "measured_on": date}
    by = {norm(s): (s, t) for s, _, t in servers(res["tools"])}
    sums = {}
    for s, _, t in servers(res["tools"]):
        sums[norm(s)] = sums.get(norm(s), 0) + t
    used, set_n = set(), 0
    for row in blocks["mcp"]:
        name = row.get("name", "")
        for cand in (name, name.split(" (")[0]):
            k = norm(cand)
            if k in sums:
                row["context_tokens"] = sums[k]
                used.add(k)
                set_n += 1
                break
    new = html
    for n in ("tokens", "mcp"):
        new = block_pattern(n).sub(lambda m, n=n: m.group(1) + dump(blocks[n]) + m.group(3), new, count=1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    r = subprocess.run([sys.executable, "-I", BUILDER, path], capture_output=True, text=True)
    if r.returncode != 0:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(html)
        print("ERROR: the build failed; the page was restored.\n" + r.stdout.strip() + r.stderr.strip())
        return 1
    print("\nPage updated: data-tokens mcp = permanent %s, deferred %s, measured %s; context_tokens set on %d of %d MCP entries."
          % (format(perm, ",d"), format(res["deferred"] or 0, ",d"), date, set_n, len(blocks["mcp"])))
    unmatched = [s for k, (s, _) in by.items() if k not in used]
    if unmatched:
        print("Servers without a matching data-mcp entry (name them like the server, or add the entry): " + ", ".join(unmatched))
    print("Build: " + r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "Build: done")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="MCP context cost from the output of /context (run by the user).",
                                 usage="python3 -I tools/mcp_cost.py <file | -> [--write [page]] [--date YYYY-MM-DD]")
    ap.add_argument("input")
    ap.add_argument("--write", nargs="?", const=DEFAULT_PAGE, default=None, metavar="page")
    ap.add_argument("--date", default=None)
    args = ap.parse_args(argv)
    date = args.date or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(date)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise ValueError
    except ValueError:
        print("ERROR: --date must be a valid date like 2026-11-20.")
        return 1
    try:
        text = sys.stdin.read() if args.input == "-" else read(args.input)
    except (OSError, UnicodeDecodeError) as e:
        print("ERROR: cannot read %s: %s" % (args.input, e))
        return 1
    res = parse(text)
    if permanent(res) is None and res["deferred"] is None and not res["tools"]:
        print("No MCP lines found. Run /context in Claude Code yourself and paste its output; the text must hold lines "
              "like 'MCP tools 18.442 ...' or 'mcp__server__tool: 1,345 tokens'.")
        return 1
    print(report(res))
    if args.write is not None:
        page = os.path.abspath(args.write)
        if not os.path.isfile(page):
            print("ERROR: %s not found." % page)
            return 1
        return write_page(page, res, date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
