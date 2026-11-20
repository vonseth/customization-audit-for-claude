#!/usr/bin/env python3
"""Builds the generated parts of audit-overview.html from the JSON data blocks at the end of the page.

Usage:  python3 -I tools/build_overview.py [path-to-html]
        Default: ../audit-overview.html (relative to this script).

The generator reads the JSON blocks, validates them, and replaces ONLY the content between the
AUTO markers (<!-- AUTO:NAME:START --> ... <!-- AUTO:NAME:END -->): SAMPLE, ASOF, KPIS, OPEN-ITEMS, TOKENS,
OVERLAPS, LIST and STYLE. Everything else (fixed bilingual texts, glossary, usage, documentation
table, footer, JSON blocks) is left byte for byte as it is. On any error it prints "ERROR: ..." and
exits with 1; the file stays unchanged. It writes only when something changes (temporary file, then
rename) and prints "unchanged" otherwise, so a second run is a no-op. Standard library only.

STYLE embeds assets/style.css; every url("fonts/....woff2") in it becomes a data: URL. A missing font
file is reported as a warning on stderr and its @font-face rule is dropped (system fonts take over);
copy the font files into assets/fonts/ and build again.

LANGUAGE
  Fixed texts exist twice: <span lang="en">..</span><span lang="de">..</span>. The page shows English
  without JavaScript; the script at the end of the page switches by html[data-lang].
  In the data blocks every "text field" (marked T below) is either a plain string (shown in both
  languages as it is) or an object {"en": "...", "de": "..."} (one key may be missing; the other one is
  used for both). Names, ids, urls and dates are plain strings.

DATA BLOCKS (script type="application/json"; objects with named keys; unknown keys are errors;
optional keys may be left out)

data-meta   object
  as_of          string ISO date YYYY-MM-DD or null     date shown as "As of ..." in the header;
                                                        if null, tokens.measured_on is used, else "As of -"
  sample         bool   true = the page holds fictional sample data (tools/sample_data.py); a bilingual
                        notice is shown at the top of the page (default false)

data-plugins   list of objects, one per installed or removed plugin / own skill
  name*          string
  source*        "own-marketplace" | "desktop" | "local" | "own-skill"     decides the group
  status*        "installed" | "disabled" | "removed"
  organization   string   shown in the details (optional, e.g. to tell two accounts apart)
  origin         T        where it comes from (repository, marketplace)
  category       T
  discussed      bool     reviewed one by one with the owner (default false)
  external_data  T        external data sources; "-" or empty = none (feeds the filter "With external data")
  tokens         string|int|T   permanent context, e.g. "~1,550"; the first number (separators ignored) sorts
  usage          T
  recommendation T        shown in the details; in the removed archive it is the reason / replacement column
  overlaps_with  T
  purpose        T        column "Purpose" in the lists; in the removed archive shown in the details

data-claudeai-skills   list of objects, skills managed on claude.ai
  name*, status* ("active" | "removed"), organization, category (T), purpose (T), tokens,
  overlaps_with (T), assessment (T: recommendation / reason)

data-mcp   list of objects, MCP servers and connectors
  name*          string
  kind*          "connector" | "plugin-mcp" | "extension" | "own-server" | "leftover" | "app"
  status*        "connected" | "not_signed_in" | "removed"       (not_signed_in goes to a collapsed subgroup)
  origin (T), discussed (bool), login (T), tokens, usage (T), recommendation (T), overlaps_with (T),
  purpose (T), security (T), organization

data-builtin   list of objects, parts of the app (listed only, not counted anywhere)
  name*, id (string, e.g. "@builtin"), function (T, column "Purpose"), usage (T), note (T)

data-candidates   list of objects, customizations that are not installed (yet)
  name*          string
  kind*          "connector" | "mcp-server" | "plugin" | "skill" | "other"     decides the subgroup
  url*           string, https://...   the only external links on the page (plus the support link)
  kind_detail (T), provider (T), purpose (T), overlaps_with (T), note (T),
  discussed (bool, default false)
  removal_reason T   if not empty the candidate moves to the removed archive ("Candidates, never installed")

data-overlaps   object
  measured_on    string ISO date or null
  fields         list of topics where customizations overlap
    topic*         T
    responsible    T     who handles which request (max 140 characters)
    members*       list (exactly one with role "core")
      name*          string    must be an installed plugin, skill or MCP server (checked by check_overview.py)
      tokens*        int       measured permanent tokens (each customization counts in one topic only)
      auto_start     bool      starts by itself (default true); false = only when called
      role*          "core" | "complement" | "replaceable"
      replaceable_by T         only for role "replaceable"
      uniqueness*    int 1..5
      reason         T         max 90 characters

data-open-items   list of T   open points, one card each (remove done items instead of marking them)

data-tokens   object or null (null = nothing measured yet)
  now*           int      measured permanent tokens per session
  first_audit    int|null value at the first audit (null = show only "now")
  first_audit_estimated  bool  true = the first-audit value is an estimate (label "estimated"), default false ("measured")
  measured_on    string ISO date or null
  parts          list of {"label": T, "tokens": int} (max 4), the stacked bar; shares come from the tokens
  note           T        extra text under the card

* = required. Counting rules of the key figures: "not yet discussed" counts plugins, MCP servers and
candidates that are not removed and have discussed = false.
"""
import base64
import datetime
import json
import os
import re
import sys
import tempfile

BLOCKS = ["meta", "plugins", "claudeai-skills", "mcp", "builtin", "candidates", "overlaps", "open-items", "tokens"]
MARKERS = ["SAMPLE", "ASOF", "KPIS", "OPEN-ITEMS", "TOKENS", "OVERLAPS", "LIST", "STYLE"]

SOURCES = ("own-marketplace", "desktop", "local", "own-skill")
PLUGIN_STATUS = ("installed", "disabled", "removed")
SKILL_STATUS = ("active", "removed")
MCP_KINDS = ("connector", "plugin-mcp", "extension", "own-server", "leftover", "app")
MCP_STATUS = ("connected", "not_signed_in", "removed")
CAND_KINDS = ("connector", "mcp-server", "plugin", "skill", "other")
ROLES = ("core", "complement", "replaceable")


class Fail(Exception):
    pass


# ---------------------------------------------------------------- text helpers

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class Text(tuple):
    """(en, de) pair of plain strings."""
    def __new__(cls, en, de=None):
        return tuple.__new__(cls, (en, en if de is None else de))

    en = property(lambda s: s[0])
    de = property(lambda s: s[1])

    def empty(self):
        return not self[0].strip() and not self[1].strip()


def bi(en, de=None):
    """Markup for a bilingual fixed text (plain when both are equal)."""
    if de is None or de == en:
        return esc(en)
    return '<span lang="en">%s</span><span lang="de">%s</span>' % (esc(en), esc(de))


def bi_raw(en, de):
    """Like bi() but with ready-made markup in both languages."""
    return '<span lang="en">%s</span><span lang="de">%s</span>' % (en, de)


def show(t):
    """Markup for a data text; empty becomes a dash."""
    if t.empty():
        return "&ndash;"
    return bi(t.en, t.de)


def attr_i18n(attr, en, de):
    """Attribute with a German swap done by the page script."""
    if en == de:
        return '%s="%s"' % (attr, esc(en))
    return '%s="%s" data-attr="%s" data-en="%s" data-de="%s"' % (attr, esc(en), attr, esc(en), esc(de))


MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
             "Oktober", "November", "Dezember"]


def date_text(iso):
    d = datetime.date.fromisoformat(iso)
    return Text("%d %s %d" % (d.day, MONTHS_EN[d.month - 1], d.year),
                "%d. %s %d" % (d.day, MONTHS_DE[d.month - 1], d.year))


def num(n, prefix=""):
    """Number with the thousands separator of each language."""
    return Text(prefix + format(n, ",d"), prefix + format(n, ",d").replace(",", "."))


def digits(s):
    m = re.search(r"\d[\d.,]*", s)
    return int(re.sub(r"[.,]", "", m.group(0))) if m else 0


def tok_short(s):
    m = re.match(r"\s*(~?\d[\d.,]*|–|-)", s)
    return m.group(1) if m else s


# ---------------------------------------------------------------- validation

T, S, B, I, U, D = "text", "str", "bool", "int", "url", "date"


def enum(*vals):
    return ("enum", vals)


TOKENS = "tokens"

SCHEMAS = {
    "plugins": ({"name": S, "source": enum(*SOURCES), "status": enum(*PLUGIN_STATUS), "organization": S,
                 "origin": T, "category": T, "discussed": B, "external_data": T, "tokens": TOKENS, "usage": T,
                 "recommendation": T, "overlaps_with": T, "purpose": T}, {"name", "source", "status"}),
    "claudeai-skills": ({"name": S, "status": enum(*SKILL_STATUS), "organization": S, "category": T, "purpose": T,
                         "tokens": TOKENS, "overlaps_with": T, "assessment": T}, {"name", "status"}),
    "mcp": ({"name": S, "kind": enum(*MCP_KINDS), "status": enum(*MCP_STATUS), "organization": S, "origin": T,
             "discussed": B, "login": T, "tokens": TOKENS, "usage": T, "recommendation": T, "overlaps_with": T,
             "purpose": T, "security": T}, {"name", "kind", "status"}),
    "builtin": ({"name": S, "id": S, "function": T, "usage": T, "note": T}, {"name"}),
    "candidates": ({"name": S, "kind": enum(*CAND_KINDS), "url": U, "kind_detail": T, "provider": T, "purpose": T,
                    "overlaps_with": T, "note": T, "discussed": B, "removal_reason": T}, {"name", "kind", "url"}),
}
DEFAULTS = {T: lambda: Text(""), S: lambda: "", B: lambda: False, I: lambda: 0, TOKENS: lambda: Text(""),
            U: lambda: ""}


def conv(value, kind, where):
    if kind == T:
        if isinstance(value, str):
            return Text(value)
        if (isinstance(value, dict) and value and set(value) <= {"en", "de"}
                and all(isinstance(v, str) for v in value.values())):
            return Text(value.get("en", value.get("de")), value.get("de", value.get("en")))
        raise Fail("%s: text expected (string or {\"en\": ..., \"de\": ...}), found %r" % (where, value))
    if kind == TOKENS:
        if isinstance(value, bool) or not isinstance(value, (str, int, dict)):
            raise Fail("%s: tokens must be a string, a number or {\"en\",\"de\"}, found %r" % (where, value))
        if isinstance(value, int):
            return num(value, "~")
        return conv(value, T, where)
    if kind == S:
        if not isinstance(value, str):
            raise Fail("%s: plain string expected, found %r" % (where, value))
        return value
    if kind == B:
        if not isinstance(value, bool):
            raise Fail("%s: true or false expected, found %r" % (where, value))
        return value
    if kind == I:
        if isinstance(value, bool) or not isinstance(value, int):
            raise Fail("%s: whole number expected, found %r" % (where, value))
        return value
    if kind == U:
        if not isinstance(value, str) or not re.match(r"^https://[^\s\"<>]+$", value):
            raise Fail("%s: address must start with https:// and contain no spaces, found %r" % (where, value))
        return value
    if kind == D:
        if value is None:
            return None
        if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            raise Fail("%s: date as YYYY-MM-DD or null expected, found %r" % (where, value))
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            raise Fail("%s: not a valid date: %r" % (where, value))
        return value
    if isinstance(kind, tuple) and kind[0] == "enum":
        if value not in kind[1]:
            raise Fail("%s: must be one of %s, found %r" % (where, " | ".join(kind[1]), value))
        return value
    raise AssertionError(kind)


def check_row(block, i, row, schema, required):
    label = "%s, entry %d" % (block, i)
    if not isinstance(row, dict):
        raise Fail("%s: object expected, found %s" % (label, type(row).__name__))
    name = row.get("name")
    if isinstance(name, str) and name:
        label += " (%s)" % name
    for k in row:
        if k not in schema:
            raise Fail("%s: unknown key %r (allowed: %s)" % (label, k, ", ".join(sorted(schema))))
    for k in sorted(required):
        if k not in row:
            raise Fail("%s: required key %r is missing" % (label, k))
    out = {}
    for k, kind in schema.items():
        if k in row:
            out[k] = conv(row[k], kind, "%s, key %s" % (label, k))
        else:
            out[k] = DEFAULTS[kind]() if not isinstance(kind, tuple) else None
    if not out["name"]:
        raise Fail("%s: name must not be empty" % label)
    return out


def read_block(html, name):
    m = re.search(r'<script type="application/json" id="data-%s">(.*?)</script>' % re.escape(name), html, re.S)
    if not m:
        raise Fail("JSON block #data-%s not found" % name)
    try:
        return json.loads(m.group(1))
    except ValueError as e:
        raise Fail("JSON block #data-%s is not valid JSON: %s" % (name, e))


def validate_overlaps(raw):
    if not isinstance(raw, dict) or set(raw) - {"measured_on", "fields"}:
        raise Fail("data-overlaps: object with the keys measured_on and fields expected")
    out = {"measured_on": conv(raw.get("measured_on"), D, "data-overlaps, key measured_on"), "fields": []}
    fields = raw.get("fields", [])
    if not isinstance(fields, list):
        raise Fail("data-overlaps: fields must be a list")
    fschema = {"topic": T, "responsible": T, "members": None}
    mschema = {"name": S, "tokens": I, "auto_start": B, "role": enum(*ROLES), "replaceable_by": T,
               "uniqueness": I, "reason": T}
    for i, f in enumerate(fields, 1):
        if not isinstance(f, dict):
            raise Fail("data-overlaps, topic %d: object expected" % i)
        for k in f:
            if k not in fschema:
                raise Fail("data-overlaps, topic %d: unknown key %r" % (i, k))
        if "topic" not in f or "members" not in f:
            raise Fail("data-overlaps, topic %d: keys topic and members are required" % i)
        topic = conv(f["topic"], T, "data-overlaps, topic %d, key topic" % i)
        label = "data-overlaps, topic %d (%s)" % (i, topic.en)
        members = f["members"]
        if not isinstance(members, list) or not members:
            raise Fail("%s: members must be a non-empty list" % label)
        ms = []
        for j, m in enumerate(members, 1):
            ml = "%s, member %d" % (label, j)
            if not isinstance(m, dict):
                raise Fail("%s: object expected" % ml)
            for k in m:
                if k not in mschema:
                    raise Fail("%s: unknown key %r" % (ml, k))
            for k in ("name", "tokens", "role", "uniqueness"):
                if k not in m:
                    raise Fail("%s: required key %r is missing" % (ml, k))
            o = {}
            for k, kind in mschema.items():
                if k in m:
                    o[k] = conv(m[k], kind, "%s, key %s" % (ml, k))
                elif k == "auto_start":
                    o[k] = True
                else:
                    o[k] = DEFAULTS[kind]() if not isinstance(kind, tuple) else None
            if o["tokens"] < 0:
                raise Fail("%s: tokens must not be negative" % ml)
            if not 1 <= o["uniqueness"] <= 5:
                raise Fail("%s: uniqueness must be between 1 and 5" % ml)
            ms.append(o)
        if sum(1 for m in ms if m["role"] == "core") != 1:
            raise Fail("%s: exactly one member with role core expected" % label)
        out["fields"].append({"topic": topic, "responsible": conv(f.get("responsible", ""), T, label + ", key responsible"),
                              "members": ms})
    return out


def validate_tokens(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - {"now", "first_audit", "first_audit_estimated", "measured_on", "parts", "note"}:
        raise Fail("data-tokens: null or an object with now, first_audit, first_audit_estimated, measured_on, parts, note expected")
    if "now" not in raw:
        raise Fail("data-tokens: required key 'now' is missing")
    out = {"now": conv(raw["now"], I, "data-tokens, key now")}
    fa = raw.get("first_audit")
    out["first_audit"] = None if fa is None else conv(fa, I, "data-tokens, key first_audit")
    est = raw.get("first_audit_estimated", False)
    if not isinstance(est, bool):
        raise Fail("data-tokens: first_audit_estimated must be true or false")
    out["first_audit_estimated"] = est
    out["measured_on"] = conv(raw.get("measured_on"), D, "data-tokens, key measured_on")
    out["note"] = conv(raw.get("note", ""), T, "data-tokens, key note")
    parts = raw.get("parts") or []
    if not isinstance(parts, list) or len(parts) > 4:
        raise Fail("data-tokens: parts must be a list with at most 4 entries")
    out["parts"] = []
    for i, p in enumerate(parts, 1):
        if not isinstance(p, dict) or set(p) != {"label", "tokens"}:
            raise Fail("data-tokens, part %d: object with label and tokens expected" % i)
        out["parts"].append({"label": conv(p["label"], T, "data-tokens, part %d, key label" % i),
                             "tokens": conv(p["tokens"], I, "data-tokens, part %d, key tokens" % i)})
    if out["parts"] and sum(p["tokens"] for p in out["parts"]) <= 0:
        raise Fail("data-tokens: the tokens of the parts add up to 0")
    return out


def load_all(html):
    """Reads and validates all blocks; returns a dict of normalized data."""
    data = {}
    for name in BLOCKS:
        raw = read_block(html, name)
        if name == "meta":
            if not isinstance(raw, dict) or set(raw) - {"as_of", "sample"}:
                raise Fail("data-meta: object with the optional keys as_of and sample expected")
            data[name] = {"as_of": conv(raw.get("as_of"), D, "data-meta, key as_of"),
                          "sample": conv(raw.get("sample", False), B, "data-meta, key sample")}
        elif name == "overlaps":
            data[name] = validate_overlaps(raw)
        elif name == "tokens":
            data[name] = validate_tokens(raw)
        elif name == "open-items":
            if not isinstance(raw, list):
                raise Fail("data-open-items: list expected")
            data[name] = [conv(x, T, "data-open-items, item %d" % i) for i, x in enumerate(raw, 1)]
        else:
            if not isinstance(raw, list):
                raise Fail("data-%s: list expected" % name)
            schema, required = SCHEMAS[name]
            rows = [check_row("data-" + name, i, r, schema, required) for i, r in enumerate(raw, 1)]
            data[name] = rows
    return data


# ---------------------------------------------------------------- fixed vocabulary

LBL = {k: Text(*v) for k, v in {
    "source": ("Source", "Quelle"), "organization": ("Organization", "Organisation"),
    "category": ("Category", "Kategorie"), "external": ("External data sources", "Externe Datenquellen"),
    "usage": ("Usage", "Nutzung"), "overlaps": ("Overlaps with", "Überschneidung mit"),
    "recommendation": ("Recommendation", "Empfehlung"), "purpose": ("Purpose", "Zweck"),
    "tokens": ("Tokens", "Tokens"), "kind": ("Kind", "Art"), "origin": ("Origin", "Herkunft"),
    "login": ("Sign-in and access", "Anmeldung und Zugriff"), "security": ("Security", "Sicherheit"),
    "id": ("Identifier", "Kennung"), "note": ("Note", "Hinweis"), "function": ("Function", "Funktion"),
    "provider": ("Provider", "Anbieter"), "address": ("Address", "Adresse"),
}.items()}

SOURCE_LABEL = {"own-marketplace": Text("Plugin from an own marketplace", "Plugin aus eigenem Marktplatz"),
                "desktop": Text("Desktop plugin", "Desktop-Plugin"), "local": Text("Local plugin", "Lokales Plugin"),
                "own-skill": Text("Own skill", "Eigener Skill")}
MCP_KIND_LABEL = {"connector": Text("claude.ai connector", "claude.ai-Connector"),
                  "plugin-mcp": Text("Plugin MCP", "Plugin-MCP"),
                  "extension": Text("Desktop extension", "Desktop-Erweiterung"),
                  "own-server": Text("Own server", "Eigener Server"), "leftover": Text("Leftover", "Rest"),
                  "app": Text("Part of the app", "Teil der App")}
CAND_KIND_LABEL = {"connector": Text("Connector"), "mcp-server": Text("MCP server", "MCP-Server"),
                   "plugin": Text("Plugin"), "skill": Text("Skill"), "other": Text("Other", "Sonstiges")}

STATUS_TAG = {  # status key -> (css class, word)
    "installed": ("t-inst", Text("installed", "installiert")), "disabled": ("t-off", Text("disabled", "deaktiviert")),
    "removed": ("t-gone", Text("removed", "entfernt")),
    "connected": ("t-inst", Text("connected", "verbunden")),
    "not_signed_in": ("t-off", Text("not signed in", "nicht angemeldet")),
    "active": ("t-inst", Text("installed", "installiert")),
}
BUILTIN_TAG = ("t-info", Text("built-in", "eingebaut"))
CAND_TAG = ("t-plan", Text("not installed", "nicht installiert"))
FILTER_KEY = {"installed": "inst", "disabled": "off", "removed": "gone", "connected": "inst",
              "not_signed_in": "off", "active": "inst"}

INFO_CLAUDEAI = Text("Managed in the Claude app under Customize → Skills.",
                     "Verwaltet in der Claude-App unter Customize → Skills.")
INFO_MCP = Text("Connected MCP servers cost permanent context (names and instructions). Plugin MCPs without "
                "sign-in stay as they are; they only go away with their plugin.",
                "Verbundene MCP-Server kosten dauerhaft Kontext (Namen und Anweisungen). Plugin-MCPs ohne Anmeldung "
                "bleiben so; sie entfallen nur mit ihrem Plugin.")
INFO_BUILTIN = Text("Part of Claude Code, comes with app updates; not installed by you, not part of the audit "
                    "and not in the key figures.",
                    "Teil von Claude Code, kommt mit App-Updates; nicht von dir installiert, nicht Teil des Audits "
                    "und nicht in den Kennzahlen.")
INFO_CAND = Text("Customizations you named but have not installed. Researched only, no security review yet. "
                 "Review before installing.",
                 "Anpassungen, die du genannt, aber nicht installiert hast. Nur recherchiert, noch keine "
                 "Sicherheitsprüfung. Vor einer Installation prüfen.")


def empty_start():
    """Empty state before the first audit."""
    return ('<p class="empty">%s</p>' % bi_raw(
        'No audit yet. Start with the first audit in <a href="docs/getting-started.md">Getting started</a>.',
        'Noch kein Audit. Beginne mit dem ersten Audit in <a href="docs/getting-started.md">Erste Schritte</a>.'))


def empty_line(en, de):
    return '<p class="empty">%s</p>' % bi(en, de)


# ---------------------------------------------------------------- entries

def tag(spec):
    cls, word = spec
    return '<span class="tag %s">%s</span>' % (cls, bi(word.en, word.de))


def entry(e, idx):
    """e: name, status (inst|off|plan|gone), tag (markup), tokens (Text), extern (bool), col (Text),
    details [(label Text, Text | ('raw', markup))], search [Text|str]."""
    s = []
    for x in e["search"]:
        s.extend([x.en, x.de] if isinstance(x, Text) else [x])
    suche = " ".join(s).lower()
    short = Text(tok_short(e["tokens"].en), tok_short(e["tokens"].de))
    out = ['<details class="entry" data-name="%s" data-status="%s" data-tokens="%d" data-extern="%s" data-index="%d" data-search="%s">'
           % (esc(e["name"].lower()), e["status"], digits(e["tokens"].en), "yes" if e["extern"] else "no", idx,
              esc(re.sub(r"\s+", " ", suche)))]
    out.append('<summary><span class="e-name">%s</span> %s <span class="e-tokens">%s</span> <span class="e-purpose">%s</span></summary>'
               % (esc(e["name"]), e["tag"], bi(short.en, short.de) if not short.empty() else "&ndash;", show(e["col"])))
    out.append('<dl class="e-details">')
    if not e["tokens"].empty() and short != e["tokens"]:
        out.append("<dt>%s</dt><dd>%s</dd>" % (bi(*LBL["tokens"]), show(e["tokens"])))
    for label, value in e["details"]:
        if isinstance(value, tuple) and value and value[0] == "raw":
            val = value[1]
        else:
            val = show(value)
        out.append("<dt>%s</dt><dd>%s</dd>" % (bi(label.en, label.de), val))
    out.append("</dl>")
    out.append("</details>")
    return ["  " + out[0]] + ["    " + x for x in out[1:-1]] + ["  " + out[-1]]


def list_html(entries, last_col, tok_col=LBL["tokens"]):
    z = ['<div class="list">',
         '<div class="head" aria-hidden="true"><span></span> <span>%s</span> <span>%s</span> '
         '<span class="h-tokens">%s</span> <span>%s</span></div>'
         % (bi("Name"), bi("Status", "Status"), bi(tok_col.en, tok_col.de), bi(last_col.en, last_col.de))]
    for i, e in enumerate(entries):
        z.extend(entry(e, i))
    z.append("</div>")
    return z


def plugin_entry(r, purpose_mode):
    cls, word = STATUS_TAG[r["status"]]
    details = [(LBL["source"], SOURCE_LABEL[r["source"]])]
    if not r["origin"].empty():
        details.append((LBL["origin"], r["origin"]))
    if r["organization"]:
        details.append((LBL["organization"], Text(r["organization"])))
    details += [(LBL["category"], r["category"]), (LBL["external"], r["external_data"]), (LBL["usage"], r["usage"]),
                (LBL["overlaps"], r["overlaps_with"]),
                (LBL["recommendation"], r["recommendation"]) if purpose_mode else (LBL["purpose"], r["purpose"])]
    ext = not r["external_data"].empty() and r["external_data"].en.strip() not in ("-", "–")
    return dict(name=r["name"], status=FILTER_KEY[r["status"]], tag=tag((cls, word)), tokens=r["tokens"], extern=ext,
                col=r["purpose"] if purpose_mode else r["recommendation"], details=details,
                search=[r["name"], SOURCE_LABEL[r["source"]], r["origin"], r["organization"], r["category"], word,
                        r["external_data"], r["tokens"], r["usage"], r["recommendation"], r["overlaps_with"], r["purpose"]])


def skill_entry(r, purpose_mode):
    cls, word = STATUS_TAG[r["status"]]
    details = [(LBL["source"], Text("claude.ai skill", "claude.ai-Skill"))]
    if r["organization"]:
        details.append((LBL["organization"], Text(r["organization"])))
    details += [(LBL["category"], r["category"]), (LBL["overlaps"], r["overlaps_with"]),
                (LBL["recommendation"], r["assessment"]) if purpose_mode else (LBL["purpose"], r["purpose"])]
    return dict(name=r["name"], status=FILTER_KEY[r["status"]], tag=tag((cls, word)), tokens=r["tokens"], extern=False,
                col=r["purpose"] if purpose_mode else r["assessment"], details=details,
                search=[r["name"], "claude.ai skill", r["organization"], r["category"], word, r["tokens"],
                        r["assessment"], r["overlaps_with"], r["purpose"]])


def mcp_entry(r, purpose_mode):
    cls, word = STATUS_TAG[r["status"]]
    details = [(LBL["kind"], MCP_KIND_LABEL[r["kind"]]), (LBL["origin"], r["origin"])]
    if r["organization"]:
        details.append((LBL["organization"], Text(r["organization"])))
    details += [(LBL["login"], r["login"]), (LBL["usage"], r["usage"]), (LBL["security"], r["security"]),
                (LBL["overlaps"], r["overlaps_with"]),
                (LBL["recommendation"], r["recommendation"]) if purpose_mode else (LBL["purpose"], r["purpose"])]
    return dict(name=r["name"], status=FILTER_KEY[r["status"]], tag=tag((cls, word)), tokens=r["tokens"], extern=True,
                col=r["purpose"] if purpose_mode else r["recommendation"], details=details,
                search=[r["name"], MCP_KIND_LABEL[r["kind"]], r["origin"], r["organization"], word, r["login"],
                        r["tokens"], r["usage"], r["recommendation"], r["overlaps_with"], r["purpose"], r["security"]])


def builtin_entry(r):
    return dict(name=r["name"], status="inst", tag=tag(BUILTIN_TAG), tokens=Text("–"), extern=False,
                col=r["function"], details=[(LBL["id"], Text(r["id"])), (LBL["note"], r["note"]), (LBL["usage"], r["usage"])],
                search=[r["name"], r["id"], BUILTIN_TAG[1], r["function"], r["usage"], r["note"]])


def cand_kind(r):
    base = CAND_KIND_LABEL[r["kind"]]
    if r["kind_detail"].empty():
        return base
    return Text("%s · %s" % (base.en, r["kind_detail"].en), "%s · %s" % (base.de, r["kind_detail"].de))


def cand_entry(r):
    link = '<a class="ni-link" href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (esc(r["url"]), esc(r["url"]))
    disc = Text("discussed", "besprochen") if r["discussed"] else Text("open", "offen")
    return dict(name=r["name"], status="plan", tag=tag(CAND_TAG), tokens=disc, extern=False, col=r["purpose"],
                details=[(LBL["kind"], cand_kind(r)), (LBL["provider"], r["provider"]), (LBL["address"], ("raw", link)),
                         (LBL["overlaps"], r["overlaps_with"]), (LBL["note"], r["note"])],
                search=[r["name"], CAND_KIND_LABEL[r["kind"]], r["kind_detail"], r["provider"], r["url"], r["purpose"],
                        r["overlaps_with"], r["note"], CAND_TAG[1], disc])


def cand_removed_entry(r):
    return dict(name=r["name"], status="gone", tag=tag(CAND_TAG), tokens=Text("–"), extern=False,
                col=r["removal_reason"],
                details=[(LBL["kind"], cand_kind(r)), (LBL["provider"], r["provider"]), (LBL["address"], Text(r["url"])),
                         (LBL["purpose"], r["purpose"]), (LBL["overlaps"], r["overlaps_with"]), (LBL["note"], r["note"])],
                search=[r["name"], CAND_KIND_LABEL[r["kind"]], r["kind_detail"], r["provider"], r["url"], r["purpose"],
                        r["overlaps_with"], r["note"], r["removal_reason"], CAND_TAG[1], STATUS_TAG["removed"][1]])


# ---------------------------------------------------------------- groups

def h3(title, n):
    return '<h3>%s <span class="count">%d</span></h3>' % (bi(title.en, title.de), n)


def info(t):
    return '<p class="group-info">%s</p>' % bi(t.en, t.de)


GROUP_TITLE = {
    "g-own": Text("Your own marketplaces", "Eigene Marktplätze"),
    "g-desktop": Text("Desktop plugins", "Desktop-Plugins"),
    "g-local": Text("Local plugins and skills", "Lokale Plugins und Skills"),
    "g-claudeai": Text("claude.ai skills", "claude.ai-Skills"),
    "g-mcp": Text("MCP servers and connectors", "MCP-Server und Connectors"),
    "g-builtin": Text("Built-in (part of Claude Code)", "Eingebaut (Teil von Claude Code)"),
    "g-candidates": Text("Not installed yet", "Noch nicht installiert"),
    "g-removed": Text("Removed", "Entfernt"),
}
CHIP_LABEL = {"g-mcp": Text("MCP servers", "MCP-Server"), "g-builtin": Text("Built-in", "Eingebaut"),
              "g-local": Text("Local plugins and skills", "Lokale Plugins und Skills")}
CAND_SUB = [("cg-connector", Text("Connectors"), "connector"), ("cg-mcp", Text("MCP servers", "MCP-Server"), "mcp-server"),
            ("cg-plugin", Text("Plugins"), "plugin"), ("cg-skill", Text("Skills"), "skill"),
            ("cg-other", Text("Other (tools, collections, web services)", "Sonstiges (Werkzeuge, Sammlungen, Webdienste)"), "other")]
REMOVED_SUB = [("rg-desktop", Text("Desktop plugins", "Desktop-Plugins")),
               ("rg-local", Text("Local plugins and skills", "Lokale Plugins und Skills")),
               ("rg-claudeai", Text("claude.ai skills", "claude.ai-Skills")),
               ("rg-mcp", Text("MCP servers and connectors", "MCP-Server und Connectors")),
               ("rg-leftovers", Text("Leftovers and clean-ups", "Reste und Bereinigungen")),
               ("rg-candidates", Text("Candidates, never installed", "Kandidaten, nie installiert"))]


def group(gid, entries, info_text=None, empty=None):
    z = ['<section class="group" id="%s">' % gid, h3(GROUP_TITLE[gid], len(entries))]
    if info_text is not None:
        z.append(info(info_text))
    if entries:
        z.extend(list_html(entries, LBL["purpose"]))
    else:
        z.append(empty)
    z.append("</section>")
    return z


def group_mcp(entries, empty):
    on = [e for e in entries if e["status"] != "off"]
    off = [e for e in entries if e["status"] == "off"]
    z = ['<section class="group" id="g-mcp">', h3(GROUP_TITLE["g-mcp"], len(entries)), info(INFO_MCP)]
    if on:
        z.extend(list_html(on, LBL["purpose"]))
    elif not off:
        z.append(empty)
    if off:
        z.append('<details class="subgroup collapse" id="sg-mcp-off">')
        z.append('<summary><h4>%s <span class="count">%d</span></h4></summary>'
                 % (bi("Plugin MCPs without sign-in", "Plugin-MCPs ohne Anmeldung"), len(off)))
        z.extend(list_html(off, LBL["purpose"]))
        z.append("</details>")
    z.append("</section>")
    return z


def group_candidates(parts, empty):
    n = sum(len(v) for v in parts.values())
    z = ['<section class="group" id="g-candidates">', h3(GROUP_TITLE["g-candidates"], n), info(INFO_CAND)]
    if not n:
        z.append(empty)
    for uid, title, _ in CAND_SUB:
        if not parts[uid]:
            continue
        z.append('<div class="subgroup" id="%s">' % uid)
        z.append('<h4>%s <span class="count">%d</span></h4>' % (bi(title.en, title.de), len(parts[uid])))
        z.extend(list_html(parts[uid], LBL["purpose"], Text("Discussed", "Besprochen")))
        z.append("</div>")
    z.append("</section>")
    return z


def group_removed(parts):
    n = sum(len(v) for v in parts.values())
    z = ['<section class="group" id="g-removed">', '<details class="collapse archive">',
         '<summary><h3>%s <span class="count">%d</span></h3></summary>' % (bi(*GROUP_TITLE["g-removed"]), n)]
    for uid, title in REMOVED_SUB:
        if not parts[uid]:
            continue
        z.append('<div class="subgroup" id="%s">' % uid)
        z.append('<h4>%s <span class="count">%d</span></h4>' % (bi(title.en, title.de), len(parts[uid])))
        z.extend(list_html(parts[uid], Text("Reason / replacement", "Grund / Ersatz")))
        z.append("</div>")
    z.append("</details>")
    z.append("</section>")
    return z


def build_groups(data):
    """Returns (entries per group dict, removed parts, candidate parts)."""
    g = {k: [] for k in GROUP_TITLE}
    removed = {u: [] for u, _ in REMOVED_SUB}
    for r in data["plugins"]:
        if r["status"] == "removed":
            removed["rg-desktop" if r["source"] == "desktop" else "rg-local"].append(plugin_entry(r, False))
        else:
            gid = {"own-marketplace": "g-own", "desktop": "g-desktop", "local": "g-local", "own-skill": "g-local"}[r["source"]]
            g[gid].append(plugin_entry(r, True))
    for r in data["claudeai-skills"]:
        if r["status"] == "removed":
            removed["rg-claudeai"].append(skill_entry(r, False))
        else:
            g["g-claudeai"].append(skill_entry(r, True))
    for r in data["mcp"]:
        if r["status"] == "removed":
            removed["rg-leftovers" if r["kind"] == "leftover" else "rg-mcp"].append(mcp_entry(r, False))
        else:
            g["g-mcp"].append(mcp_entry(r, True))
    g["g-builtin"] = [builtin_entry(r) for r in data["builtin"]]
    cands = {u: [] for u, _, _ in CAND_SUB}
    for r in data["candidates"]:
        if r["removal_reason"].empty():
            cands[next(u for u, _, k in CAND_SUB if k == r["kind"])].append(cand_entry(r))
        else:
            removed["rg-candidates"].append(cand_removed_entry(r))
    g["g-candidates"] = [e for v in cands.values() for e in v]
    g["g-removed"] = [e for v in removed.values() for e in v]
    return g, removed, cands


def audit_started(data):
    return bool(data["plugins"] or data["claudeai-skills"] or data["mcp"] or data["builtin"] or data["candidates"]
                or data["overlaps"]["fields"] or data["open-items"] or data["tokens"] or data["meta"]["as_of"])


def list_markup(data):
    g, removed, cands = build_groups(data)
    if not any(g[k] for k in g):
        return empty_start()
    none = empty_line("None.", "Keine.")
    chips = []
    z = []
    order = ["g-own", "g-desktop", "g-local", "g-claudeai", "g-mcp", "g-builtin", "g-candidates", "g-removed"]
    for gid in order:
        if gid in ("g-own", "g-removed") and not g[gid]:
            continue
        if gid == "g-own":
            z += group(gid, g[gid])
        elif gid == "g-mcp":
            z += group_mcp(g[gid], none)
        elif gid == "g-claudeai":
            z += group(gid, g[gid], INFO_CLAUDEAI, none)
        elif gid == "g-builtin":
            z += group(gid, g[gid], INFO_BUILTIN, none)
        elif gid == "g-candidates":
            z += group_candidates(cands, none)
        elif gid == "g-removed":
            z += group_removed(removed)
        else:
            z += group(gid, g[gid], None, none)
        chips.append(gid)
    nav = ['<nav class="chips" %s>' % attr_i18n("aria-label", "Jump to a group", "Zu einer Gruppe springen")]
    for gid in chips:
        lab = CHIP_LABEL.get(gid, GROUP_TITLE[gid])
        nav.append('<a href="#%s">%s</a>' % (gid, bi(lab.en, lab.de)))
    nav.append("</nav>")
    return "\n".join(nav + z)


# ---------------------------------------------------------------- key figures, open items, tokens, overlaps

def kpi_cards(data):
    pl = data["plugins"]
    inst = sum(1 for r in pl if r["status"] != "removed")
    off = sum(1 for r in pl if r["status"] == "disabled")
    gone = sum(1 for r in pl if r["status"] == "removed")
    sk = data["claudeai-skills"]
    sk_on = sum(1 for r in sk if r["status"] == "active")
    sk_gone = len(sk) - sk_on
    mc = data["mcp"]
    mc_on = sum(1 for r in mc if r["status"] == "connected")
    mc_off = sum(1 for r in mc if r["status"] == "not_signed_in")
    cand = sum(1 for r in data["candidates"] if r["removal_reason"].empty())
    open_n = (sum(1 for r in pl if r["status"] != "removed" and not r["discussed"])
              + sum(1 for r in mc if r["status"] != "removed" and not r["discussed"])
              + sum(1 for r in data["candidates"] if r["removal_reason"].empty() and not r["discussed"]))
    cards = [
        (inst, "plugins and skills installed (%d disabled)" % off, "Plugins und Skills installiert (davon %d deaktiviert)" % off),
        (sk_on, "claude.ai skills active (%d removed)" % sk_gone, "claude.ai-Skills aktiv (%d entfernt)" % sk_gone),
        (mc_on, "MCP servers connected (%d not signed in)" % mc_off, "MCP-Server verbunden (%d nicht angemeldet)" % mc_off),
        (cand, "not installed yet", "noch nicht installiert"),
        (gone, "plugins and skills removed", "Plugins und Skills entfernt"),
        (open_n, "not yet discussed", "noch nicht besprochen"),
    ]
    return "\n".join('<div class="card"><b>%d</b> <span>%s</span></div>' % (n, bi(en, de)) for n, en, de in cards)


def open_items_markup(data):
    items = data["open-items"]
    if items:
        z = ['<ul class="open-items">']
        for t in items:
            z.append('  <li><span class="tag">%s</span><span>%s</span></li>' % (bi("open", "offen"), bi(t.en, t.de)))
        z.append("</ul>")
        return "\n".join(z)
    if audit_started(data):
        return empty_line("No open items.", "Keine offenen Punkte.")
    return empty_start()


def sample_markup(data):
    if not data["meta"]["sample"]:
        return ""
    cmd = "<code>python3 -I tools/sample_data.py remove</code>"
    return '<div class="sample-banner" role="note">%s</div>' % bi_raw(
        "<b>Sample data</b> &mdash; this is not your installation. Remove it with: " + cmd,
        "<b>Beispieldaten</b> &mdash; das ist nicht deine Installation. Entfernen mit: " + cmd)


def asof_markup(data):
    iso = data["meta"]["as_of"] or (data["tokens"] or {}).get("measured_on")
    if not iso:
        return bi("As of —.", "Stand —.")
    d = date_text(iso)
    return bi("As of %s." % d.en, "Stand %s." % d.de)


def tokens_markup(data):
    t = data["tokens"]
    if t is None:
        if audit_started(data):
            return empty_line("Tokens not measured yet.", "Tokens noch nicht gemessen.")
        return empty_start()
    z = ['<div class="tokencard">', '<div class="compare">']
    first = t["first_audit"]
    if first is not None:
        n = num(first, "~")
        z.append('  <div class="value w-first"><span>%s</span><b>%s</b><span>%s</span></div>' % (bi("at first audit", "beim ersten Audit"), bi(n.en, n.de), bi("estimated", "geschätzt") if t["first_audit_estimated"] else bi("measured", "gemessen")))
        z.append('  <div class="arrow" aria-hidden="true">→</div>')
    n = num(t["now"], "~")
    z.append('  <div class="value w-now"><span>%s</span><b>%s</b><span>%s</span></div>'
             % (bi("now", "jetzt"), bi(n.en, n.de), bi("measured", "gemessen")))
    z.append("</div>")
    if first:
        diff = first - t["now"]
        pct = round(100.0 * abs(diff) / first)
        amt = num(abs(diff), "~")
        if diff > 0:
            z.append('<p class="saving"><b>%s</b> · %s</p>' % (
                bi("−%d%%" % pct, "−%d %%" % pct),
                bi_raw("%s tokens saved per session" % esc(amt.en), "%s Tokens je Sitzung eingespart" % esc(amt.de))))
        elif diff < 0:
            z.append('<p class="saving"><b>%s</b> · %s</p>' % (
                bi("+%d%%" % pct, "+%d %%" % pct),
                bi_raw("%s tokens more per session" % esc(amt.en), "%s Tokens mehr je Sitzung" % esc(amt.de))))
        else:
            z.append('<p class="saving">%s</p>' % bi("No change since the first audit.", "Keine Änderung seit dem ersten Audit."))
    if t["parts"]:
        total = sum(p["tokens"] for p in t["parts"])
        label_en = ", ".join("%s %s" % (p["label"].en, num(p["tokens"], "~").en) for p in t["parts"])
        label_de = ", ".join("%s %s" % (p["label"].de, num(p["tokens"], "~").de) for p in t["parts"])
        z.append('<div class="stack" role="img" %s>' % attr_i18n("aria-label", label_en, label_de))
        z.append("  " + "".join('<i class="p%d" style="width:%.1f%%"></i>' % (i, 100.0 * p["tokens"] / total)
                                for i, p in enumerate(t["parts"], 1) if p["tokens"] > 0))
        z.append("</div>")
        z.append('<div class="stack-legend">')
        for i, p in enumerate(t["parts"], 1):
            n = num(p["tokens"], "~")
            z.append('  <span class="p%d">%s %s</span>' % (i, bi(p["label"].en, p["label"].de), bi(n.en, n.de)))
        z.append("</div>")
    en, de = [], []
    if t["measured_on"]:
        d = date_text(t["measured_on"])
        en.append("Measured on %s.<br>" % esc(d.en))
        de.append("Gemessen am %s.<br>" % esc(d.de))
    en.append("Counted are the short descriptions Claude reads at the start of every session; the tokens are "
              "estimated from them. Connected MCP servers cost additional context.")
    de.append("Gezählt sind die Kurzbeschreibungen, die Claude zu Beginn jeder Sitzung liest; daraus sind die "
              "Tokens geschätzt. Verbundene MCP-Server kosten zusätzlich Kontext.")
    if not t["note"].empty():
        en.append(" " + esc(t["note"].en))
        de.append(" " + esc(t["note"].de))
    z.append('<p class="small">%s</p>' % bi_raw("".join(en), "".join(de)))
    z.append("</div>")
    return "\n".join(z)


ROLE_LABEL = {"core": ("r-core", Text("most value", "größter Mehrwert")),
              "complement": ("r-comp", Text("complement", "Ergänzung")),
              "replaceable": ("r-rep", Text("replaceable", "ersetzbar"))}


def tok(n):
    n = int(round(n, -1)) if n >= 100 else int(n)
    return num(n, "~")


def overlaps_markup(data, now_total):
    ov = data["overlaps"]
    fields = ov["fields"]
    if not fields:
        return empty_line("No overlaps recorded.", "Keine Überschneidungen erfasst.") if audit_started(data) else empty_start()
    fields = sorted(fields, key=lambda f: -sum(m["tokens"] for m in f["members"]))
    total = sum(m["tokens"] for f in fields for m in f["members"])
    biggest = max(sum(m["tokens"] for m in f["members"]) for f in fields)
    count = sum(len(f["members"]) for f in fields)
    tk = tok(total)
    of_en = " (of %s)" % num(now_total, "~").en if now_total else ""
    of_de = " (von %s)" % num(now_total, "~").de if now_total else ""
    z = ['<div class="cards ov-cards">',
         '<div class="card"><b>%d</b> <span>%s</span></div>' % (len(fields), bi("topics with overlap", "Themenfelder mit Überschneidung")),
         '<div class="card"><b>%d</b> <span>%s</span></div>' % (count, bi("customizations involved", "beteiligte Anpassungen")),
         '<div class="card"><b>%s</b> <span>%s</span></div>' % (bi(tk.en, tk.de), bi("tokens per session" + of_en, "Tokens je Sitzung" + of_de)),
         "</div>",
         '<p class="ov-legend"><span class="l-auto">%s</span> <span class="l-call">%s</span></p>'
         % (bi("starts by itself", "springt von selbst an"), bi("only when called", "nur auf Aufruf"))]
    order = ["core", "complement", "replaceable"]
    for f in fields:
        ms = sorted(f["members"], key=lambda m: (order.index(m["role"]), -m["tokens"]))
        s = sum(m["tokens"] for m in ms)
        z.append('<details class="ov-topic">')
        t = tok(s)
        z.append('<summary><span class="ov-head"><span class="ov-title">%s <span class="count">%d</span></span> '
                 '<span class="ov-tok">%s</span></span>' % (show(f["topic"]), len(ms), bi(t.en, t.de)))
        seg = "".join('<i class="%s" style="width:%.1f%%" title="%s"></i>' % (
            "auto" if m["auto_start"] else "call", 100.0 * m["tokens"] / s if s else 0, esc(m["name"])) for m in ms)
        lab = ", ".join("%s %s" % (m["name"], tok(m["tokens"]).en) for m in ms)
        lab_de = ", ".join("%s %s" % (m["name"], tok(m["tokens"]).de) for m in ms)
        z.append('<span class="ov-bar" style="width:%.1f%%" role="img" %s>%s</span>'
                 % (max(3.0, 100.0 * s / biggest) if biggest else 100.0, attr_i18n("aria-label", lab, lab_de), seg))
        z.append('<span class="ov-members">%s</span>' % "".join(
            '<span class="ov-m">%s %s</span>' % (esc(m["name"]), bi(*tok(m["tokens"]))) for m in ms))
        if not f["responsible"].empty():
            z.append('<span class="ov-resp">%s %s</span></summary>' % (bi("Responsible:", "Zuständig:"), show(f["responsible"])))
        else:
            z.append("</summary>")
        heads = [("Customization", "Anpassung"), ("Tokens", "Tokens"), ("Role", "Rolle"),
                 ("Uniqueness", "Alleinstellung"), ("Reason", "Begründung")]
        z.append('<table class="ov-table"><thead><tr>%s</tr></thead><tbody>'
                 % "".join("<th>%s</th>" % bi(a, b) for a, b in heads))
        for m in ms:
            cls, word = ROLE_LABEL[m["role"]]
            by = ""
            if m["role"] == "replaceable" and not m["replaceable_by"].empty():
                by = '<span class="ov-by">%s</span>' % bi_raw("by " + esc(m["replaceable_by"].en), "durch " + esc(m["replaceable_by"].de))
            call = "" if m["auto_start"] else ' <span class="ov-call">%s</span>' % bi("only when called", "nur auf Aufruf")
            lv = m["uniqueness"]
            lab5 = bi_raw("%d of 5" % lv, "%d von 5" % lv)
            lvl = "".join('<i class="on"></i>' if k < lv else "<i></i>" for k in range(5))

            def td(i, inner):
                a, b = heads[i]
                return '<td data-l-en="%s" data-l-de="%s">%s</td>' % (esc(a), esc(b), inner)
            tt = tok(m["tokens"])
            z.append("<tr>%s%s%s%s%s</tr>" % (
                td(0, esc(m["name"]) + call), td(1, bi(tt.en, tt.de)),
                td(2, '<span class="ov-role %s">%s</span>%s' % (cls, bi(word.en, word.de), by)),
                td(3, '<span class="ov-level" role="img" %s>%s</span>' % (
                    attr_i18n("aria-label", "%d of 5" % lv, "%d von 5" % lv), lvl)),
                td(4, show(m["reason"]))))
        z.append("</tbody></table>")
        z.append("</details>")
    note_en, note_de = "", ""
    if ov["measured_on"]:
        d = date_text(ov["measured_on"])
        note_en, note_de = "Measured on %s.<br>" % esc(d.en), "Gemessen am %s.<br>" % esc(d.de)
    z.append('<p class="small ov-note">%s</p>' % bi_raw(
        note_en + "Sums come from the measurement per customization. Each customization counts in one topic only. "
        "Roles are recommendations: nothing is removed without going through it with you first.",
        note_de + "Summen aus der Messung je Anpassung. Jede Anpassung zählt nur in einem Themenfeld. Die Rollen "
        "sind Empfehlungen: Entfernt wird nur nach einer Einzelbesprechung mit dir."))
    return "\n".join(z)


# ---------------------------------------------------------------- style, markers, main

def style_markup(page_path):
    assets = os.path.join(os.path.dirname(os.path.abspath(page_path)), "assets")
    with open(os.path.join(assets, "style.css"), encoding="utf-8") as f:
        css = f.read()
    missing = []

    def embed(m):
        path = os.path.join(assets, m.group(1))
        if not os.path.exists(path):
            missing.append(m.group(1))
            return m.group(0)
        with open(path, "rb") as f:
            return 'url("data:font/woff2;base64,%s")' % base64.b64encode(f.read()).decode("ascii")
    css = re.sub(r'url\("(fonts/[^"]+\.woff2)"\)', embed, css)
    for name in missing:
        sys.stderr.write("WARNING: font file assets/%s is missing; its @font-face rule is left out\n" % name)
        css = re.sub(r'@font-face\{[^}]*url\("%s"\)[^}]*\}\n?' % re.escape(name), "", css)
    return "<style>\n" + css.strip() + "\n</style>"


def replace_marker(html, name, content):
    start, end = "<!-- AUTO:%s:START -->" % name, "<!-- AUTO:%s:END -->" % name
    a, b = html.find(start), html.find(end)
    if a < 0 or b < 0:
        raise Fail("marker %s is missing" % (start if a < 0 else end))
    if html.count(start) != 1 or html.count(end) != 1 or b < a:
        raise Fail("markers AUTO:%s are not unique or in the wrong order" % name)
    return html[:a + len(start)] + "\n" + content + "\n" + html[b:]


def replace_inline(html, name, content):
    """Marker pair inside a line (no line breaks added)."""
    start, end = "<!-- AUTO:%s:START -->" % name, "<!-- AUTO:%s:END -->" % name
    a, b = html.find(start), html.find(end)
    if a < 0 or b < 0 or html.count(start) != 1 or html.count(end) != 1 or b < a:
        raise Fail("markers AUTO:%s are missing, not unique or in the wrong order" % name)
    return html[:a + len(start)] + content + html[b:]


def render(html, page_path):
    data = load_all(html)
    now_total = data["tokens"]["now"] if data["tokens"] else None
    out = replace_inline(html, "SAMPLE", sample_markup(data))
    out = replace_inline(out, "ASOF", asof_markup(data))
    out = replace_marker(out, "KPIS", kpi_cards(data))
    out = replace_marker(out, "OPEN-ITEMS", open_items_markup(data))
    out = replace_marker(out, "TOKENS", tokens_markup(data))
    out = replace_marker(out, "OVERLAPS", overlaps_markup(data, now_total))
    out = replace_marker(out, "LIST", list_markup(data))
    out = replace_marker(out, "STYLE", style_markup(page_path))
    return out, data


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "audit-overview.html")
    try:
        with open(path, encoding="utf-8", newline="") as f:
            html = f.read()
        new, data = render(html, path)
    except (Fail, OSError) as e:
        print("ERROR: %s\nFile unchanged." % e)
        return 1
    print("  plugins %d, claude.ai skills %d, MCP %d, built-in %d, candidates %d, overlap topics %d, open items %d"
          % (len(data["plugins"]), len(data["claudeai-skills"]), len(data["mcp"]), len(data["builtin"]),
             len(data["candidates"]), len(data["overlaps"]["fields"]), len(data["open-items"])))
    if new == html:
        print("unchanged")
        return 0
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        os.chmod(tmp, os.stat(path).st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    print("changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
