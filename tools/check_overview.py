#!/usr/bin/env python3
"""Checks audit-overview.html (read-only).

Usage:  python3 -I tools/check_overview.py [path-to-html] [--strict] [--inventory inventory.tsv]
        Default: ../audit-overview.html (relative to this script).

Checks (the expected values are computed from the JSON data blocks of the page):
  1  Names and order of the entries in every group match the data; jump chips match the groups.
  2  Field values of every entry (in both languages) are present in the entry.
  3  Counts: span.count of each group and subgroup = number of entries = expected number.
  4  Key figures: the six cards (and the three cards of the overlaps section) match recalculated values.
  5  The generator is idempotent: tools/build_overview.py run on a copy reports "unchanged".
  6  Tag balance: opened and closed HTML elements match.
  7  No external resources: no <link>, no remote scripts, images, fonts, fetch(); the only https links are
     the candidate links a.ni-link (one per listed candidate, only in the candidates group) and the
     support link in the footer. CSS is embedded; url() in it only as embedded font (data:font/woff2).
  8  Language frames: every <span lang="en"> has a <span lang="de"> sibling right after it (and the
     other way round); <html> has lang and the script sets data-lang.
  9  Jump bar: exactly five section links, all targets exist; every jump chip target exists.
 10  Documentation table: all expected files are listed; every listed file or folder exists
     (missing = WARNING; with --strict = FAIL).
 11  Content rules: purpose / reason columns <= 90 characters, "responsible" <= 140, overlap reason <= 90
     (each language); exactly one core per overlap topic; overlap members are installed customizations;
     "replaceable_by" only for role replaceable; "overlaps_with" naming a removed customization (WARNING);
     as-of date in the header matches the data; fonts: embedded @font-face rules match assets/style.css
     (missing font files = WARNING; with --strict = FAIL).
 12  History: data-history is sorted with unique dates; with two or more snapshots the token card shows exactly
     one row per snapshot (date, tokens, numbers, bar width scaled to the maximum), with fewer none.
 13  Tool documentation: every tools/*.py (except the internal modules paths.py and schema.py) is mentioned by file name in README.md or
     docs/manual.md (missing = WARNING; with --strict = FAIL).
 14  Optional (--inventory FILE, the TSV written by tools/inventory.py): every inventory entry of the kinds
     local-plugin, desktop-plugin, claude-ai-skill and own-skill appears on the page (FAIL if not);
     installed entries on the page that are not in the inventory (WARNING).
 15  MCP cost (always runs, listed after 14): with data-tokens "mcp" the token card shows exactly one line
     "MCP servers add ~N tokens per session ..." with the numbers and the date of the data (both languages);
     without it no such line. Every MCP entry with "context_tokens" shows "Context size (all tools)" with that
     number, every entry without it shows no such row.

Output: one line per check, PASS, WARN or FAIL, with details. Exit code 1 if any check fails, else 0.
The file is not changed. Standard library only.
"""
import collections
import html as htmllib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(HERE, "build_overview.py")
DEFAULT = os.path.join(HERE, "..", "audit-overview.html")

spec = importlib.util.spec_from_file_location("build_overview", BUILDER)
bo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bo)

GROUPS = ["g-own", "g-desktop", "g-local", "g-claudeai", "g-mcp", "g-builtin", "g-candidates", "g-removed"]
COUNTED_TAGS = ["details", "summary", "section", "dl", "div", "table", "ul", "li", "p", "span", "h2", "h3", "h4", "a", "nav",
                "button", "select", "footer", "header", "main", "thead", "tbody", "tr", "td", "th", "b", "i"]
VOID = {"meta", "link", "br", "img", "input", "hr"}
EXPECTED_DOCS = ["README.md", "CLAUDE.md", "CHANGELOG.md", "LICENSE", "DESIGN.md", "docs/getting-started.md",
                 "docs/review-guide.md", "docs/explanation-template.md", "docs/overview-structure.md",
                 "docs/agent-briefs.md", "tools/", "examples/sample-data.json", "reports/"]
SUPPORT_URL = "https://paypal.me/vonseth"


def esc(s):
    return bo.esc(s)


def both(t):
    """Both languages of a Text as a list of unique strings."""
    return [t.en] if t.en == t.de else [t.en, t.de]


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []


class Tree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = Node("#root", [], None)
        self.cur = self.root
        self.open, self.close = collections.Counter(), collections.Counter()
        self.errors = []
        self.all = []

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        self.all.append(n)
        if tag in COUNTED_TAGS:
            self.open[tag] += 1
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        self.all.append(n)

    def handle_endtag(self, tag):
        if tag in COUNTED_TAGS:
            self.close[tag] += 1
        if self.cur.tag == tag:
            self.cur = self.cur.parent
        else:
            self.errors.append("</%s> without matching open element (inside <%s>)" % (tag, self.cur.tag))


def parse(text):
    t = Tree()
    t.feed(text)
    return t


def section(text, gid):
    """Markup of a group section by id."""
    m = re.search(r'<section class="group" id="%s">' % re.escape(gid), text)
    if not m:
        return ""
    end = text.find("</section>", m.end())
    return text[m.end():end]


def expected_groups(data):
    """Independent recomputation: group id -> list of (name, record, kind)."""
    g = {k: [] for k in GROUPS}
    removed = []
    for r in data["plugins"]:
        if r["status"] == "removed":
            removed.append((r["name"], r, "plugin"))
        else:
            gid = {"own-marketplace": "g-own", "desktop": "g-desktop"}.get(r["source"], "g-local")
            g[gid].append((r["name"], r, "plugin"))
    for r in data["claudeai-skills"]:
        (removed if r["status"] == "removed" else g["g-claudeai"]).append((r["name"], r, "skill"))
    mc = data["mcp"]
    for r in [x for x in mc if x["status"] == "connected"] + [x for x in mc if x["status"] == "not_signed_in"]:
        g["g-mcp"].append((r["name"], r, "mcp"))
    for r in data["builtin"]:
        g["g-builtin"].append((r["name"], r, "builtin"))
    for kind in ("connector", "mcp-server", "plugin", "skill", "other"):
        for r in data["candidates"]:
            if r["kind"] == kind and r["removal_reason"].empty():
                g["g-candidates"].append((r["name"], r, "candidate"))
    # removed archive in the order of the subgroups
    def sub(item):
        n, r, k = item
        if k == "plugin":
            return 0 if r["source"] == "desktop" else 1
        if k == "skill":
            return 2
        if k == "mcp":
            return 4 if r["kind"] == "leftover" else 3
        return 5
    for r in data["mcp"]:
        if r["status"] == "removed":
            removed.append((r["name"], r, "mcp"))
    for r in data["candidates"]:
        if not r["removal_reason"].empty():
            removed.append((r["name"], r, "candidate-removed"))
    sub_ix = lambda it: 5 if it[2] == "candidate-removed" else sub(it)
    g["g-removed"] = sorted(removed, key=sub_ix)  # stable: keeps data order inside a subgroup
    # claude.ai skills and plugins in the removed list: builder order is plugins, skills, mcp, candidates by subgroup
    return g


def expected_kpis(data):
    pl, sk, mc = data["plugins"], data["claudeai-skills"], data["mcp"]
    listed = [r for r in data["candidates"] if r["removal_reason"].empty()]
    return [
        sum(1 for r in pl if r["status"] != "removed"), sum(1 for r in sk if r["status"] == "active"),
        sum(1 for r in mc if r["status"] == "connected"), len(listed), sum(1 for r in pl if r["status"] == "removed"),
        sum(1 for r in pl if r["status"] != "removed" and not r["discussed"])
        + sum(1 for r in mc if r["status"] != "removed" and not r["discussed"])
        + sum(1 for r in listed if not r["discussed"]),
    ]


def field_values(kind, r):
    """Texts that must appear in the entry (list of Text or str)."""
    if kind == "plugin":
        v = [r["name"], r["category"], r["external_data"], r["usage"], r["recommendation"], r["overlaps_with"], r["purpose"],
             r["origin"]]
        if r["organization"]:
            v.append(r["organization"])
        return v
    if kind == "skill":
        return [r["name"], r["category"], r["overlaps_with"], r["assessment"], r["purpose"]]
    if kind == "mcp":
        return [r["name"], r["origin"], r["login"], r["usage"], r["security"], r["overlaps_with"], r["recommendation"], r["purpose"]]
    if kind == "builtin":
        return [r["name"], r["id"], r["function"], r["usage"], r["note"]]
    if kind == "candidate":
        return [r["name"], r["provider"], r["purpose"], r["overlaps_with"], r["note"], r["url"]]
    return [r["name"], r["provider"], r["purpose"], r["overlaps_with"], r["note"], r["url"], r["removal_reason"]]


def check_names(text, data, g):
    problems = []
    for gid in GROUPS:
        body = section(text, gid)
        got = [htmllib.unescape(x) for x in re.findall(r'<span class="e-name">(.*?)</span>', body)]
        want = [n for n, _, _ in g[gid]]
        if gid in ("g-own", "g-removed") and not want and body:
            problems.append("%s is rendered although it has no entries" % gid)
        elif want and got != want:
            problems.append("%s: expected %s, found %s" % (gid, want, got))
        elif not want and got:
            problems.append("%s: expected no entries, found %s" % (gid, got))
    return problems


def check_fields(text, g):
    problems, n = [], 0
    for gid in GROUPS:
        entries = re.findall(r'<details class="entry".*?</details>', section(text, gid), re.S)
        for (name, r, kind), ent in zip(g[gid], entries):
            for v in field_values(kind, r):
                variants = both(v) if isinstance(v, bo.Text) else [v]
                for s in variants:
                    if s and esc(s) not in ent:
                        problems.append("%s, %r: value missing: %r" % (gid, name, s[:60]))
                    n += 1
    return problems, n


def check_counts(text, g):
    problems = []
    for gid in GROUPS:
        body = section(text, gid)
        want = len(g[gid])
        if not want:
            continue
        m = re.search(r'<span class="count">(\d+)</span>', body)
        n = len(re.findall(r'<details class="entry"', body))
        if not m or int(m.group(1)) != n or n != want:
            problems.append("%s: count %s, entries %d, expected %d" % (gid, m.group(1) if m else "-", n, want))
    for gid, subs in (("g-removed", [u for u, _ in bo.REMOVED_SUB]), ("g-candidates", [u for u, _, _ in bo.CAND_SUB])):
        body = section(text, gid)
        parts = re.findall(r'<div class="subgroup" id="([a-z-]+)">\s*<h4>.*?<span class="count">(\d+)</span></h4>(.*?)(?=<div class="subgroup"|$)', body, re.S)
        for uid, c, b in parts:
            n = len(re.findall(r'<details class="entry"', b))
            if int(c) != n:
                problems.append("%s/%s: count %s, entries %d" % (gid, uid, c, n))
        got = sum(len(re.findall(r'<details class="entry"', b)) for _, _, b in parts)
        if got != len(g[gid]):
            problems.append("%s: subgroups hold %d entries, expected %d" % (gid, got, len(g[gid])))
    return problems


def check_kpis(text, data):
    m = re.search(r"<!-- AUTO:KPIS:START -->(.*?)<!-- AUTO:KPIS:END -->", text, re.S)
    got = [int(x) for x in re.findall(r'<div class="card"><b>(\d+)</b>', m.group(1))] if m else []
    want = expected_kpis(data)
    problems = []
    if got != want:
        problems.append("key figures: expected %s, found %s" % (want, got))
    ov = data["overlaps"]["fields"]
    m = re.search(r"<!-- AUTO:OVERLAPS:START -->(.*?)<!-- AUTO:OVERLAPS:END -->", text, re.S)
    body = m.group(1) if m else ""
    if ov:
        cards = re.findall(r'<div class="card"><b>(.*?)</b>', body)
        wantn = [str(len(ov)), str(sum(len(f["members"]) for f in ov))]
        if [c for c in cards[:2]] != wantn:
            problems.append("overlap cards: expected %s, found %s" % (wantn, cards[:2]))
        topics = re.findall(r'<details class="ov-topic">', body)
        if len(topics) != len(ov):
            problems.append("overlap topics: expected %d, found %d" % (len(ov), len(topics)))
        titles = [htmllib.unescape(re.sub(r"<[^>]+>", "", t)) for t in re.findall(r'<span class="ov-title">(.*?) <span class="count">', body)]
        # sorted by token sum, descending
        sums = [sum(m_["tokens"] for m_ in f["members"]) for f in ov]
        order = sorted(range(len(ov)), key=lambda i: -sums[i])
        want_titles = [ov[i]["topic"] for i in order]
        if len(titles) == len(ov):
            for t, w in zip(titles, want_titles):
                if t != "%s%s" % (w.en, w.de) and t != w.en:
                    problems.append("overlap topic order: %r does not match %r" % (t, w.en))
    return problems, want


def check_generator(path, raw):
    problems = []
    with tempfile.TemporaryDirectory(prefix="overview-check-") as tmp:
        copy = os.path.join(tmp, "audit-overview.html")
        shutil.copyfile(path, copy)
        assets = os.path.join(os.path.dirname(os.path.abspath(path)), "assets")
        if os.path.isdir(assets):
            shutil.copytree(assets, os.path.join(tmp, "assets"))
        version = os.path.join(os.path.dirname(os.path.abspath(path)), "VERSION")
        if os.path.isfile(version):
            shutil.copyfile(version, os.path.join(tmp, "VERSION"))
        run = subprocess.run([sys.executable, "-I", BUILDER, copy], cwd=tmp, capture_output=True, text=True)
        with open(copy, "rb") as f:
            after = f.read()
    if run.returncode != 0:
        problems.append("generator exit code %d: %s" % (run.returncode, run.stdout.strip()))
    elif "unchanged" not in run.stdout:
        problems.append("generator reports a change on a copy (the page is out of date): run tools/build_overview.py")
    if after != raw:
        problems.append("generator changed the copy (bytes %d -> %d)" % (len(raw), len(after)))
    return problems


def check_tags(tree):
    problems = []
    for t in COUNTED_TAGS:
        if tree.open[t] != tree.close[t]:
            problems.append("<%s>: opened %d, closed %d" % (t, tree.open[t], tree.close[t]))
    problems += tree.errors[:5]
    if len(tree.errors) > 5:
        problems.append("... and %d more errors" % (len(tree.errors) - 5))
    if tree.cur is not tree.root:
        problems.append("not closed at the end: <%s>" % tree.cur.tag)
    return problems


def check_external(text, tree, n_listed):
    problems = []
    ni = support = 0
    for n in tree.all:
        a = n.attrs
        if n.tag == "link":
            problems.append("<link %s> found (the CSS is embedded)" % a)
        if (n.tag == "a" and a.get("class") == "ni-link" and (a.get("href") or "").startswith("https://")
                and a.get("target") == "_blank" and a.get("rel") == "noopener noreferrer"
                and set(a) == {"class", "href", "target", "rel"}):
            ni += 1
            continue
        if n.tag == "a" and a.get("href") == SUPPORT_URL and a.get("rel") == "noopener noreferrer":
            support += 1
            continue
        for k in ("src", "href", "action", "srcset", "data", "poster"):
            v = (a.get(k) or "").strip()
            if re.match(r"^(https?:)?//", v, re.I):
                problems.append("<%s %s=%r>" % (n.tag, k, v))
    head_style = text[:text.find("</style>")] if "</style>" in text else ""
    script_part = text[text.find("</style>"):]
    if re.search(r"@import", head_style, re.I):
        problems.append("@import found")
    for u in re.findall(r"url\(\s*['\"]?([^'\")]+)", head_style):
        if not u.startswith("data:font/woff2;base64,"):
            problems.append("url() in the embedded CSS is not an embedded font: %s" % u[:60])
    for w in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon", "importScripts"):
        if w in script_part:
            problems.append("script call %r found" % w)
    in_cand = len(re.findall(r'<a class="ni-link"', section(text, "g-candidates")))
    if ni != n_listed or in_cand != n_listed:
        problems.append("a.ni-link: %d valid, %d in the candidates group, expected %d" % (ni, in_cand, n_listed))
    if support != 1:
        problems.append("support link %s: %d found, expected 1" % (SUPPORT_URL, support))
    if text.count("<style>") != 1 or "<!-- AUTO:STYLE:START -->\n<style>" not in text:
        problems.append("embedded <style> block between AUTO:STYLE is missing or appears more than once")
    return problems


def check_lang(tree):
    problems = []
    root = tree.root.children[0] if tree.root.children and tree.root.children[0].tag == "html" else None
    if root is None or not root.attrs.get("lang"):
        problems.append("<html> has no lang attribute")
    pairs = 0
    for n in tree.all:
        if n.tag == "html":
            continue
        lg = n.attrs.get("lang")
        if lg is None:
            continue
        if n.tag != "span" or lg not in ("en", "de"):
            problems.append("unexpected lang attribute on <%s lang=%r>" % (n.tag, lg))
            continue
        sib = n.parent.children
        i = sib.index(n)
        if lg == "en":
            nxt = sib[i + 1] if i + 1 < len(sib) else None
            if not (nxt and nxt.tag == "span" and nxt.attrs.get("lang") == "de"):
                problems.append('<span lang="en"> without a following <span lang="de"> sibling (inside <%s %s>)'
                                % (n.parent.tag, n.parent.attrs.get("id") or n.parent.attrs.get("class") or ""))
            pairs += 1
        else:
            prv = sib[i - 1] if i > 0 else None
            if not (prv and prv.tag == "span" and prv.attrs.get("lang") == "en"):
                problems.append('<span lang="de"> without a preceding <span lang="en"> sibling (inside <%s %s>)'
                                % (n.parent.tag, n.parent.attrs.get("id") or n.parent.attrs.get("class") or ""))
    return problems, pairs


def ids_of(tree):
    return {n.attrs["id"] for n in tree.all if n.attrs.get("id")}


def check_jump(tree):
    problems = []
    ids = ids_of(tree)
    bar = next((n for n in tree.all if n.attrs.get("id") == "jumpbar"), None)
    if bar is None:
        return ["nav#jumpbar not found"]
    links = [c for c in bar.children if c.tag == "a"]
    if len(links) != 5:
        problems.append("jump bar has %d section links, expected 5" % len(links))
    for a in links:
        h = a.attrs.get("href", "")
        if not h.startswith("#") or h[1:] not in ids:
            problems.append("jump bar target missing: %s" % h)
    for n in tree.all:
        if n.tag == "nav" and n.attrs.get("class") == "chips":
            for a in n.children:
                if a.tag != "a":
                    continue
                h = a.attrs.get("href", "")
                if not h.startswith("#") or h[1:] not in ids:
                    problems.append("jump chip target missing: %s" % h)
    for a in tree.all:
        if a.tag == "a" and (a.attrs.get("href") or "").startswith("#") and a.attrs["href"][1:] not in ids:
            problems.append("anchor target missing: %s" % a.attrs["href"])
    return sorted(set(problems))


def check_docs(tree, base, strict):
    problems, warns = [], []
    doc = next((n for n in tree.all if n.attrs.get("id") == "documentation"), None)
    if doc is None:
        return ["section #documentation not found"], []
    hrefs = []

    def walk(n):
        if n.tag == "a" and n.attrs.get("href"):
            hrefs.append(n.attrs["href"])
        for c in n.children:
            walk(c)
    walk(doc)
    for want in EXPECTED_DOCS:
        if want not in hrefs:
            problems.append("documentation table does not list %s" % want)
    for h in hrefs:
        if h.startswith(("#", "http")):
            continue
        if not os.path.exists(os.path.join(base, h)):
            (problems if strict else warns).append("listed but missing: %s" % h)
    return problems, warns


def lens(t):
    return max(len(t.en), len(t.de))


def check_content(text, tree, data, base, strict):
    problems, warns = [], []
    for kind, rows, f_col, f_reason in (("plugins", data["plugins"], "purpose", "recommendation"),
                                        ("claudeai-skills", data["claudeai-skills"], "purpose", "assessment"),
                                        ("mcp", data["mcp"], "purpose", "recommendation")):
        for r in rows:
            f = f_reason if r["status"] == "removed" else f_col
            if lens(r[f]) > 90:
                problems.append("%s %r: column text (%s) has %d characters, limit 90" % (kind, r["name"], f, lens(r[f])))
    for r in data["builtin"]:
        if lens(r["function"]) > 90:
            problems.append("builtin %r: function has %d characters, limit 90" % (r["name"], lens(r["function"])))
    for r in data["candidates"]:
        f = "purpose" if r["removal_reason"].empty() else "removal_reason"
        if lens(r[f]) > 90:
            problems.append("candidate %r: %s has %d characters, limit 90" % (r["name"], f, lens(r[f])))
    installed = ({r["name"] for r in data["plugins"] if r["status"] != "removed"}
                 | {r["name"] for r in data["claudeai-skills"] if r["status"] == "active"}
                 | {r["name"] for r in data["mcp"] if r["status"] != "removed"})
    for f in data["overlaps"]["fields"]:
        label = f["topic"].en
        if lens(f["responsible"]) > 140:
            problems.append("overlap %r: responsible has %d characters, limit 140" % (label, lens(f["responsible"])))
        if sum(1 for m in f["members"] if m["role"] == "core") != 1:
            problems.append("overlap %r: exactly one core expected" % label)
        for m in f["members"]:
            if m["name"] not in installed:
                problems.append("overlap %r: member %r is not an installed customization" % (label, m["name"]))
            if lens(m["reason"]) > 90:
                problems.append("overlap %r, %r: reason has %d characters, limit 90" % (label, m["name"], lens(m["reason"])))
            if m["role"] != "replaceable" and not m["replaceable_by"].empty():
                problems.append("overlap %r, %r: replaceable_by only for role replaceable" % (label, m["name"]))
            if m["role"] == "replaceable" and m["replaceable_by"].empty():
                warns.append("overlap %r, %r: role replaceable without replaceable_by" % (label, m["name"]))
    gone = ({r["name"] for r in data["plugins"] if r["status"] == "removed"}
            | {r["name"] for r in data["claudeai-skills"] if r["status"] == "removed"}
            | {r["name"] for r in data["mcp"] if r["status"] == "removed"}) - installed
    for kind, rows in (("plugins", data["plugins"]), ("claudeai-skills", data["claudeai-skills"]), ("mcp", data["mcp"])):
        for r in rows:
            if r["status"] == "removed":
                continue
            for n in gone:
                if len(n) >= 4 and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(n), r["overlaps_with"].en + " " + r["overlaps_with"].de):
                    warns.append("%s %r: overlaps_with names the removed customization %r" % (kind, r["name"], n))
    # as-of date
    iso = data["meta"]["as_of"] or (data["tokens"] or {}).get("measured_on")
    sub = re.search(r'<p class="sub">(.*?)<br>', text, re.S)
    want = bo.asof_markup(data)
    if not sub or sub.group(1) != "<!-- AUTO:ASOF:START -->%s<!-- AUTO:ASOF:END -->" % want:
        problems.append("the as-of line in the header does not match the data (date %s)" % iso)
    # fonts
    css_path = os.path.join(base, "assets", "style.css")
    try:
        css = open(css_path, encoding="utf-8").read()
        want_fonts = re.findall(r'url\("(fonts/[^"]+\.woff2)"\)', css)
        have = len(re.findall(r"@font-face", text[:text.find("</style>")]))
        missing = [f for f in want_fonts if not os.path.exists(os.path.join(base, "assets", f))]
        for f in missing:
            (problems if strict else warns).append("font file missing: assets/%s" % f)
        if not missing and have != len(want_fonts):
            problems.append("embedded @font-face rules: %d, assets/style.css has %d" % (have, len(want_fonts)))
    except OSError:
        problems.append("assets/style.css is missing")
    return problems, warns


def check_history(text, data):
    hist = data["history"]
    problems = []
    m = re.search(r"<!-- AUTO:TOKENS:START -->(.*?)<!-- AUTO:TOKENS:END -->", text, re.S)
    body = m.group(1) if m else ""
    rows = re.findall(r'<li class="hist-row[^"]*">(.*?)</li>', body, re.S)
    if len(hist) < 2:
        if rows or 'class="history"' in body:
            problems.append("history timeline is shown with %d snapshot(s); it needs at least 2" % len(hist))
        return problems, len(hist)
    if len(rows) != len(hist):
        return ["history rows: expected %d, found %d" % (len(hist), len(rows))], len(hist)
    top = max(h["tokens"] for h in hist) or 1
    for h, row in zip(hist, rows):
        d, n = bo.date_text(h["date"]), bo.num(h["tokens"], "~")
        if bo.bi(d.en, d.de) not in row:
            problems.append("history %s: date missing in the row" % h["date"])
        if bo.bi(n.en, n.de) not in row:
            problems.append("history %s: tokens %d missing in the row" % (h["date"], h["tokens"]))
        w = re.search(r'<i style="width:([\d.]+)%"', row)
        if not w or abs(float(w.group(1)) - 100.0 * h["tokens"] / top) > 0.06:
            problems.append("history %s: bar width %s, expected %.1f%%" % (h["date"], w.group(1) if w else "-", 100.0 * h["tokens"] / top))
        counts = bo.bi("%d installed, %d removed, %d candidates" % (h["installed"], h["removed"], h["candidates"]),
                       "%d installiert, %d entfernt, %d Kandidaten" % (h["installed"], h["removed"], h["candidates"]))
        if counts not in row:
            problems.append("history %s: numbers missing in the row" % h["date"])
        if not h["note"].empty() and bo.bi(h["note"].en, h["note"].de) not in row:
            problems.append("history %s: note missing in the row" % h["date"])
    return problems, len(hist)


def check_mcp_cost(text, data):
    problems = []
    m = re.search(r"<!-- AUTO:TOKENS:START -->(.*?)<!-- AUTO:TOKENS:END -->", text, re.S)
    body = m.group(1) if m else ""
    lines = re.findall(r'<p class="mcp-line">(.*?)</p>', body, re.S)
    mc = (data["tokens"] or {}).get("mcp")
    if not mc:
        if lines:
            problems.append("MCP line is shown but data-tokens has no mcp")
    else:
        p, d = bo.num(mc["permanent"], "~"), bo.num(mc["deferred"], "~")
        en = "MCP servers add %s tokens per session" % p.en
        de = "MCP-Server kosten zusätzlich %s Tokens je Sitzung" % p.de
        if mc["measured_on"]:
            dt = bo.date_text(mc["measured_on"])
            en += " (measured %s)" % dt.en
            de += " (gemessen am %s)" % dt.de
        en += "; another %s load only when needed." % d.en if mc["deferred"] else "."
        de += "; weitere %s werden nur bei Bedarf geladen." % d.de if mc["deferred"] else "."
        if len(lines) != 1:
            problems.append("MCP line: expected exactly 1, found %d" % len(lines))
        elif lines[0] != bo.bi_raw(esc(en), esc(de)):
            problems.append("MCP line does not match the data: %s" % re.sub(r"<[^>]+>", "|", lines[0])[:160])
    label = bo.bi(*bo.LBL["context"])
    entries = {htmllib.unescape(re.search(r'<span class="e-name">(.*?)</span>', e).group(1)): e
               for e in re.findall(r'<details class="entry".*?</details>', section(text, "g-mcp") + section(text, "g-removed"), re.S)
               if re.search(r'<span class="e-name">', e)}
    n = 0
    for r in data["mcp"]:
        ent = entries.get(r["name"])
        if ent is None:
            continue
        if r["context_tokens"] is None:
            if label in ent:
                problems.append("%s: shows a context size but the data has none" % r["name"])
            continue
        n += 1
        c = bo.num(r["context_tokens"])
        want = "<dt>%s</dt><dd>%s</dd>" % (label, bo.bi("%s tokens" % c.en, "%s Tokens" % c.de))
        if want not in ent:
            problems.append("%s: context size %d missing in the details" % (r["name"], r["context_tokens"]))
    return problems, n


def check_tool_docs(base, strict):
    """Every tools/*.py (except the internal modules paths.py and schema.py) must be named in README.md or docs/manual.md."""
    tools = os.path.join(base, "tools")
    if not os.path.isdir(tools):
        return [], []
    corpus = ""
    for rel in ("README.md", os.path.join("docs", "manual.md")):
        try:
            corpus += open(os.path.join(base, rel), encoding="utf-8").read() + "\n"
        except OSError:
            pass
    missing = ["tools/%s is not mentioned in README.md or docs/manual.md" % f
               for f in sorted(os.listdir(tools)) if f.endswith(".py") and f not in ("paths.py", "schema.py") and f not in corpus]
    return (missing, []) if strict else ([], missing)


def check_inventory(inv_path, data):
    problems, warns = [], []
    try:
        lines = open(inv_path, encoding="utf-8").read().splitlines()
    except OSError as e:
        return ["cannot read the inventory: %s" % e], []
    head = lines[0].split("\t") if lines else []
    if "source" not in head or "name" not in head:
        return ["inventory has no columns source and name (expected output of tools/inventory.py)"], []
    si, ni = head.index("source"), head.index("name")
    inv = set()
    for ln in lines[1:]:
        c = ln.split("\t")
        if len(c) > max(si, ni) and c[si] in ("local-plugin", "desktop-plugin", "claude-ai-skill", "own-skill"):
            inv.add(c[ni])
    page = ({r["name"] for r in data["plugins"] if r["status"] != "removed"}
            | {r["name"] for r in data["claudeai-skills"] if r["status"] == "active"})
    for n in sorted(inv - page):
        problems.append("in the inventory but not on the page: %s" % n)
    for n in sorted(page - inv):
        warns.append("on the page but not in the inventory: %s" % n)
    return problems, warns


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="backslashreplace")
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        sys.exit(0)
    strict = "--strict" in args
    args = [a for a in args if a != "--strict"]
    inv = None
    if "--inventory" in args:
        i = args.index("--inventory")
        inv = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
        if inv is None:
            print("ERROR: --inventory needs a file", file=sys.stderr)
            return 1
    path = os.path.abspath(args[0] if args else DEFAULT)
    base = os.path.dirname(path)
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        raw = open(path, "rb").read()
        data = bo.load_all(text)
    except (OSError, bo.Fail) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 1
    tree = parse(text)
    g = expected_groups(data)
    results = []

    def add(num, title, problems, info="", warns=()):
        status = "FAIL" if problems else ("WARN" if warns else "PASS")
        results.append((num, title, status, problems, warns, info))

    add(1, "names and order", check_names(text, data, g), "%d entries" % sum(len(v) for v in g.values()))
    p, n = check_fields(text, g)
    add(2, "field values", p, "%d values" % n)
    add(3, "counts", check_counts(text, g))
    p, kp = check_kpis(text, data)
    add(4, "key figures", p, str(kp))
    add(5, "generator idempotent", check_generator(path, raw))
    add(6, "tag balance", check_tags(tree))
    add(7, "no external resources", check_external(text, tree, len(g["g-candidates"])))
    p, pairs = check_lang(tree)
    add(8, "language frames", p, "%d en/de pairs" % pairs)
    add(9, "jump bar and chips", check_jump(tree))
    p, w = check_docs(tree, base, strict)
    add(10, "documentation table", p, "", w)
    p, w = check_content(text, tree, data, base, strict)
    add(11, "content rules and fonts", p, "", w)
    p, n = check_history(text, data)
    add(12, "history", p, "%d snapshots" % n)
    p, w = check_tool_docs(base, strict)
    add(13, "tool documentation", p, "", w)
    if inv:
        p, w = check_inventory(inv, data)
        add(14, "inventory comparison", p, "", w)
    p, n = check_mcp_cost(text, data)
    add(15, "MCP cost", p, "%d context sizes" % n)
    failed = 0
    for num, title, status, problems, warns, info in results:
        print("%-4s %2d  %s%s" % (status, num, title, (" (%s)" % info) if info else ""))
        for x in problems:
            print("       - %s" % x)
        for x in warns:
            print("       ! %s" % x)
        failed += status == "FAIL"
    print("%d of %d checks passed%s" % (sum(1 for r in results if r[2] != "FAIL"), len(results),
                                        "" if not failed else "; %d FAILED" % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
