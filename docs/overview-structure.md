# Structure of the overview page

`audit-overview.html` is one self-contained file: the stylesheet and the fonts are embedded (as data URLs), there is no external resource, and the page is complete without JavaScript. The authoritative description of the data model is the docstring at the top of `tools/build_overview.py`; this page summarizes it and does not replace it.

## Sections, top to bottom

1. **Sample notice** (only while sample data is loaded).
2. **Jump bar** with five entries: Open items, Tokens, Overlaps, Customizations, Help (the documentation section). The DE | EN toggle sits at its right end.
3. **Header** with the title, "As of <date>" and six key figure cards.
4. **Open items:** one card per open point.
5. **Tokens per session:** a dark card with "now" (and, if known, the value at the first audit), the saving, a stacked bar and a short note.
6. **Overlaps:** topics where customizations overlap, with measured permanent tokens, responsibility and a role per member.
7. **Customizations:** legend, search, sort and filters, a "Jump to:" row of links to the groups, then the list in eight groups.
8. **Documentation, Glossary, Usage:** three collapsible sections, maintained by hand.
9. **Footer** (note on the usage column, author, support link, license, "Not affiliated with Anthropic").
10. **Data blocks** and the script.

### Key figures (six cards)

1. Plugins and skills installed (of which disabled): entries of `data-plugins` that are not removed.
2. claude.ai skills active (removed): entries of `data-claudeai-skills`.
3. MCP servers connected (not signed in): entries of `data-mcp`.
4. Not installed yet: entries of `data-candidates` without a `removal_reason`.
5. Plugins and skills removed.
6. Not yet discussed: entries of plugins, MCP servers and candidates that are not removed and have `discussed = false`.

### Groups of the list

| id | Group | Content |
|---|---|---|
| `g-own` | Your own marketplaces | `source` = `own-marketplace` |
| `g-desktop` | Desktop plugins | `source` = `desktop` |
| `g-local` | Local plugins and skills | `source` = `local` or `own-skill` |
| `g-claudeai` | claude.ai skills | active entries of `data-claudeai-skills` |
| `g-mcp` | MCP servers and connectors | `data-mcp` (those not signed in sit in a collapsed subgroup) |
| `g-builtin` | Built-in (part of Claude Code) | `data-builtin`; listed only, not counted anywhere |
| `g-candidates` | Not installed yet | `data-candidates`, in subgroups by kind |
| `g-removed` | Removed | A collapsed archive with subgroups for desktop, local, claude.ai skills, MCP, leftovers and candidates that were never installed |

Each entry is a collapsible row: name, status tag, tokens, purpose in the closed row; details and recommendation inside. In the removed archive the last column is the reason or replacement.

## Bilingual frame

- Fixed texts exist twice: `<span lang="en">...</span><span lang="de">...</span>`. Without JavaScript the page shows English.
- The script at the end sets `html[data-lang]` from the browser language and offers the DE | EN toggle.
- In the data blocks every text field is either a plain string (shown in both languages as it is) or an object `{"en": "...", "de": "..."}`. One key may be missing; the other is then used for both. Names, ids, URLs and dates are plain strings.

## Data blocks

At the end of the page, as `<script type="application/json" id="data-...">`. Unknown keys are errors; `*` means required. Full key lists are in the docstring of `tools/build_overview.py`.

| Block | Type | Holds |
|---|---|---|
| `data-meta` | object | `as_of` (ISO date or null), `sample` (true while sample data is loaded) |
| `data-plugins` | list | Plugins and own skills: `name*`, `source*` (`own-marketplace`, `desktop`, `local`, `own-skill`), `status*` (`installed`, `disabled`, `removed`), `organization`, `origin`, `category`, `discussed`, `external_data`, `tokens`, `usage`, `recommendation`, `overlaps_with`, `purpose` |
| `data-claudeai-skills` | list | `name*`, `status*` (`active`, `removed`), `organization`, `category`, `purpose`, `tokens`, `overlaps_with`, `assessment` |
| `data-mcp` | list | `name*`, `kind*` (`connector`, `plugin-mcp`, `extension`, `own-server`, `leftover`, `app`), `status*` (`connected`, `not_signed_in`, `removed`), `origin`, `discussed`, `login`, `tokens`, `usage`, `recommendation`, `overlaps_with`, `purpose`, `security`, `organization` |
| `data-builtin` | list | `name*`, `id`, `function`, `usage`, `note` |
| `data-candidates` | list | `name*`, `kind*` (`connector`, `mcp-server`, `plugin`, `skill`, `other`), `url*` (https), `kind_detail`, `provider`, `purpose`, `overlaps_with`, `note`, `discussed`, `removal_reason` |
| `data-overlaps` | object | `measured_on`, `fields`: topics with `topic*`, `responsible`, and `members*` (`name*`, `tokens*`, `auto_start`, `role*`, `replaceable_by`, `uniqueness*` 1 to 5, `reason`) |
| `data-open-items` | list | Open points, one card each (remove done items instead of marking them) |
| `data-tokens` | object or null | `now*`, `first_audit`, `first_audit_estimated` (true shows "estimated" under the first value, default "measured"), `measured_on`, `parts` (max 4, for the stacked bar), `note` |

Rules worth knowing:

- Subtotals per group are counts only. Token totals appear only as measured values in the tokens section, never as a sum of per-row estimates.
- Overlaps: exactly one member per topic has the role `core`; a member must be an installed customization; `replaceable_by` only for the role `replaceable`; each customization counts in one topic only; `responsible` up to 140 characters, `reason` up to 90.
- The purpose and reason columns hold at most 90 characters (per language).
- Candidate URLs are the only external links on the page (plus the support link in the footer).

## Generated versus hand-edited

`tools/build_overview.py` replaces only the content between the markers `<!-- AUTO:NAME:START -->` and `<!-- AUTO:NAME:END -->` for these names: SAMPLE, ASOF, KPIS, OPEN-ITEMS, TOKENS, OVERLAPS, LIST, STYLE. Everything else is left byte for byte as it is:

- **Generated:** sample notice, "As of" date, key figures, open items, tokens card, overlaps section, the list with all groups, and the embedded style (from `assets/style.css` and `assets/fonts/`).
- **Hand-edited:** the data blocks (your data), the documentation table, the glossary, the usage section and the footer text.

The build runs on any error with "ERROR: ..." and exit code 1 and leaves the file unchanged. It writes only when something changes and prints "unchanged" otherwise.

To change the look, edit `assets/style.css` (the source), then build. Do not edit the embedded copy in the HTML.

## Rebuild and check

After every change to a data block:

```text
python3 -I tools/build_overview.py
python3 -I tools/check_overview.py
```

Optional: `python3 -I tools/build_overview.py path/to/other.html` builds another file.

`check_overview.py` is read-only and prints PASS, WARN or FAIL per check; the exit code is 1 if any check fails. It verifies, among other things, that names and order in every group match the data, counts and key figures are right, the generator is idempotent, HTML tags are balanced, no external resources are used, both language frames are present, the jump bar has five working links, the documentation table lists existing files, and content length rules hold.

Options:

- `--strict`: warnings about missing files or fonts become failures.
- `--inventory <file.tsv>`: also compares the page with the inventory written by `tools/inventory.py` (a customization in the inventory but not on the page is a failure; the reverse is a warning).

## Moving existing data in

```text
python3 -I tools/import_data.py --export <file.json> [page]      # write the data blocks of the page to a JSON file
python3 -I tools/import_data.py <file.json> [--replace] [page]   # import such a file into a page and rebuild
```

The JSON file has the shape of `examples/sample-data.json`: one key per data block (`meta`, `plugins`, `claudeai-skills`, `mcp`, `builtin`, `candidates`, `overlaps`, `open-items`, `tokens`); a missing block counts as empty, an unknown key is an error. The import first writes the blocks into a temporary copy of the page and builds it there, so schema errors are reported without touching your page. It refuses to run when the page already holds data (sample or real) unless `--replace` is given, and it never modifies the input file. Exporting and importing the result again gives a byte-identical page. Use it to back up your data or to move it into a newer download of the project.

## Sample data

A fictional data set shows what a filled page looks like:

```text
python3 -I tools/sample_data.py load      # fill every block from examples/sample-data.json and rebuild
python3 -I tools/sample_data.py status    # tells whether sample data is on the page
python3 -I tools/sample_data.py remove    # empty all blocks again and rebuild (sample data only)
```

While the sample is loaded the page shows a notice at the top. Remove it before your first real audit. `load` refuses to run (page unchanged) if the page already holds your real data, and `remove` only ever removes sample data, so your own entries cannot be overwritten or deleted by mistake. Both rebuild the page afterwards.
