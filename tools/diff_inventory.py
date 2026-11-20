#!/usr/bin/env python3
"""Shows what changed since the last audit: current inventory versus audit-overview.html (read-only).

Usage:
    python3 -I tools/diff_inventory.py [--inventory file.tsv] [--threshold PERCENT] [page]

    page          path to the overview page (default: ../audit-overview.html next to this script)
    --inventory   read a TSV written by tools/inventory.py instead of scanning now
    --threshold   token change in percent that counts as a difference (default 20); a change
                  must also be at least 50 tokens, so tiny skills do not create noise

Examples:
    python3 -I tools/diff_inventory.py
    python3 -I tools/inventory.py now.tsv >/dev/null; python3 -I tools/diff_inventory.py --inventory now.tsv
    python3 -I tools/diff_inventory.py --threshold 10 my-copy.html

Without --inventory the scan of tools/inventory.py runs in-process (so
CUSTOMIZATION_AUDIT_HOME works as usual). Nothing is written anywhere.

What is reported, grouped by kind (local plugins, desktop plugins, own skills, claude.ai skills):
  1. new      installed now, not on the page (or only on the page as "removed" -> see 3)
  2. gone     on the page as installed / disabled / active, not found anymore
  3. status   page and inventory disagree (installed vs disabled, broken own skill,
              listed as removed on the page but present again)
  4. tokens   estimate differs: inventory tokens = description_chars / 3.7 (as everywhere in this
              project); page tokens = first number of the page's "tokens" field ("~1,550" = 1550).
              Reported if the difference is at least the threshold percent of the page value AND
              at least 50 tokens. Entries without a readable page number are skipped.

Matching rule (names are compared case-insensitive, spaces and underscores count as "-"):
  Every name is turned into a set of keys. "name@marketplace" gives "name@marketplace" and "name";
  "Display (inner)" (desktop plugins) gives the whole text, "display" and "inner". An inventory entry
  matches a page entry when their key sets share at least one key. Plugins are compared with page
  "plugins" (any source), claude.ai skills with page "claudeai-skills"; the two lists are never mixed.
  If the same name exists in several organizations, the page entry whose organization starts like
  the inventory one is preferred; otherwise any entry with that name counts as known. Own agents
  (~/.claude/agents) have no counterpart on the page and are ignored. MCP servers are not compared.

Exit code: 0 = no changes, 1 = changes found, 2 = error (unreadable page or TSV, bad arguments).
Empty page (no audit yet): says so and lists everything as new (exit 1, or 0 if nothing is installed).
Standard library only.
"""
import argparse
import contextlib
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PAGE = os.path.join(HERE, "..", "audit-overview.html")
MIN_TOKENS = 50
CHARS_PER_TOKEN = 3.7

GROUPS = [("local", "Local plugins"), ("desktop", "Desktop plugins"),
          ("own-skill", "Own skills"), ("claude-ai", "claude.ai skills")]
SRC_GROUP = {"local-plugin": "local", "desktop-plugin": "desktop",
             "own-skill": "own-skill", "claude-ai-skill": "claude-ai"}
PAGE_GROUP = {"own-marketplace": "local", "local": "local", "desktop": "desktop", "own-skill": "own-skill"}


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_tsv(text):
    """Rows of the inventory table as dicts (stops at the blank line before the summary)."""
    lines = text.splitlines()
    if not lines or not lines[0].startswith("source\t"):
        raise ValueError("not an inventory table (header line starting with 'source' missing)")
    head = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            break
        parts = ln.split("\t")
        if len(parts) < len(head):
            parts += [""] * (len(head) - len(parts))
        rows.append(dict(zip(head, parts)))
    return rows


def scan_inventory():
    inv = load_module("inventory", "inventory.py")
    out = io.StringIO()
    old_argv = sys.argv
    sys.argv = ["inventory.py"]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            inv.main()
    finally:
        sys.argv = old_argv
    return parse_tsv(out.getvalue())


def norm(s):
    return re.sub(r"[\s_]+", "-", str(s).strip().lower())


def keys(name):
    name = str(name)
    ks = {norm(name)}
    base = name.split("@", 1)[0]
    ks.add(norm(base))
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", base)
    if m:
        ks.add(norm(m.group(1)))
        ks.add(norm(m.group(2)))
    ks.discard("")
    return ks


def text_of(v):
    """Text field of the page: plain string or {"en": .., "de": ..}."""
    if isinstance(v, dict):
        return str(v.get("en") or v.get("de") or "")
    return "" if v is None else str(v)


def page_tokens(v):
    """First number in the page's tokens field ("~1,550" -> 1550), or None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d[\d.,']*", text_of(v))
    if not m:
        return None
    s = m.group(0).rstrip(".,'")
    if re.fullmatch(r"\d{1,3}(?:[.,']\d{3})+", s):
        return int(re.sub(r"[.,']", "", s))
    try:
        return int(round(float(s.replace(",", "."))))
    except ValueError:
        return None


def find(entries, name, org):
    """Page entries matching an inventory name; those of the same organization first."""
    ks = keys(name)
    hit = [e for e in entries if ks & e["keys"]]
    if org:
        same = [e for e in hit if e["org"] and (e["org"].startswith(org) or org.startswith(e["org"]))]
        if same:
            return same
    return hit


def inv_status(row):
    st = row["status"]
    if row["source"] == "local-plugin":
        return "disabled" if st == "disabled" else "installed"
    if row["source"] == "own-skill":
        return "broken" if st.startswith("BROKEN") else "installed"
    return "installed"


def compare(rows, plugins, skills, threshold):
    """Returns {group: {"new": [...], "gone": [...], "status": [...], "tokens": [...]}} (lines of text)."""
    res = {g: {"new": [], "gone": [], "status": [], "tokens": []} for g, _ in GROUPS}
    pe = [{"keys": keys(p.get("name", "")), "org": str(p.get("organization") or ""), "raw": p,
           "group": PAGE_GROUP.get(p.get("source"), "local")} for p in plugins if isinstance(p, dict)]
    se = [{"keys": keys(s.get("name", "")), "org": str(s.get("organization") or ""), "raw": s,
           "group": "claude-ai"} for s in skills if isinstance(s, dict)]
    seen = set()
    for r in rows:
        g = SRC_GROUP.get(r["source"])
        if g is None:
            continue
        pool = se if g == "claude-ai" else pe
        hit = find(pool, r["name"], r["organization"])
        label = r["name"] + (" (organization %s)" % r["organization"] if r["organization"] else "")
        if not hit:
            res[g]["new"].append("%s  [~%d tokens]" % (label, round(int(r["description_chars"] or 0) / CHARS_PER_TOKEN)))
            continue
        e = hit[0]
        seen.update(id(x) for x in hit)
        page_st = e["raw"].get("status")
        now = inv_status(r)
        if g == "claude-ai":
            page_st = {"active": "installed"}.get(page_st, page_st)
        if page_st != now:
            res[g]["status"].append("%s: page says %s, now %s" % (label, page_st, now))
        if page_st == "removed":
            continue
        pt = page_tokens(e["raw"].get("tokens"))
        if pt is not None:
            nt = round(int(r["description_chars"] or 0) / CHARS_PER_TOKEN)
            d = nt - pt
            if abs(d) >= MIN_TOKENS and abs(d) * 100 >= threshold * max(pt, 1):
                res[g]["tokens"].append("%s: page ~%d, now ~%d tokens (%+d)" % (label, pt, nt, d))
    for e in pe + se:
        if id(e) not in seen and e["raw"].get("status") in ("installed", "disabled", "active"):
            org = " (organization %s)" % e["org"] if e["org"] else ""
            res[e["group"]]["gone"].append("%s%s  [page status: %s]" % (e["raw"].get("name"), org, e["raw"].get("status")))
    return res


def report(res, empty_page, sample):
    lines = []
    if empty_page:
        lines.append("The page holds no audit data yet (no audit so far): everything installed is listed as new.")
    elif sample:
        lines.append("Note: the page holds fictional sample data, not your own audit.")
    titles = [("new", "NEW (installed now, not on the page)"),
              ("gone", "GONE (on the page as installed, not found anymore)"),
              ("status", "STATUS DIFFERS"),
              ("tokens", "TOKEN ESTIMATE DIFFERS")]
    total = 0
    for g, gname in GROUPS:
        if not any(res[g].values()):
            continue
        lines.append("")
        lines.append(gname)
        for k, title in titles:
            if res[g][k]:
                lines.append("  " + title)
                lines.extend("    - " + x for x in res[g][k])
                total += len(res[g][k])
    lines.append("")
    lines.append("%d change(s) found since the last audit." % total if total else "No changes since the last audit.")
    return lines, total


def main(argv=None):
    ap = argparse.ArgumentParser(description="Changes since the last audit (read-only).", add_help=True)
    ap.add_argument("page", nargs="?", default=DEFAULT_PAGE)
    ap.add_argument("--inventory", help="TSV from tools/inventory.py (default: scan now)")
    ap.add_argument("--threshold", type=float, default=20.0, help="token change in percent (default 20)")
    a = ap.parse_args(argv)
    if a.threshold < 0:
        print("ERROR: --threshold must not be negative.")
        return 2
    try:
        sd = load_module("sample_data", "sample_data.py")
        with open(a.page, encoding="utf-8", newline="") as f:
            blocks = sd.read_blocks(f.read())
    except (OSError, SystemExit) as e:
        print("ERROR: cannot read the page %s: %s" % (a.page, e))
        return 2
    try:
        if a.inventory:
            with open(a.inventory, encoding="utf-8") as f:
                rows = parse_tsv(f.read())
        else:
            rows = scan_inventory()
    except (OSError, ValueError) as e:
        print("ERROR: cannot read the inventory: %s" % e)
        return 2
    plugins, skills = blocks.get("plugins") or [], blocks.get("claudeai-skills") or []
    if not isinstance(plugins, list) or not isinstance(skills, list):
        print("ERROR: the data blocks plugins / claudeai-skills of the page are not lists.")
        return 2
    empty_page = not plugins and not skills
    res = compare(rows, plugins, skills, a.threshold)
    lines, total = report(res, empty_page, sd.is_sample(blocks))
    print("\n".join(lines))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
