# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 1.3.0 – 2026-11-20

### Added

- `tools/diff_inventory.py`: shows what changed since the last audit (new, gone, status, token change above a threshold) by comparing the current inventory with the page. Read-only.
- `tools/check_versions.py`: offline version check of local plugins against the local marketplace copies (version field, else commits); reports "unknown" with a reason when it cannot tell. Read-only, no network.
- `tools/mcp_cost.py`: measures the context cost of MCP servers from the text the user copies out of `/context` (desktop app and CLI formats); `--write` stores it on the page. Claude never runs `/context` itself.
- `tools/history.py`: `snapshot` appends the key numbers of an audit to the page, `list` prints them.
- `tools/backup.py`: `create`, `list`, `show` and `restore` for backups in `~/.claude/backups/` with a `manifest.json` (checksums); restore asks for confirmation and makes a safety backup first. The only tool that writes outside the project folder.
- Data: block `data-history` (list of snapshots) and the optional keys `data-tokens.mcp` (`permanent`, `deferred`, `measured_on`) and `data-mcp[].context_tokens`.
- Overview page: "History" timeline in the token card (from two snapshots), one line with the measured MCP cost, row "Context size (all tools)" in the details of MCP servers; Usage section and documentation table list the new functions.
- `check_overview.py`: check 12 (history), 13 (every tool is documented in README.md or docs/manual.md), 14 (inventory comparison, optional) and 15 (MCP cost).
- Documentation: README (features, tool table, privacy exception), manual (token card, running an audit, history and backups, FAQ, glossary), getting started, review guide, overview structure, agent briefs, `CLAUDE.md` working rules.

### Changed

- Review guide and agent brief L: local plugins are checked with `check_versions.py`; agent L only covers desktop plugins and claude.ai skills (and what the tool reports as unknown).
- Backups before changes are made with `backup.py create`; the old `~/.claude/backups/<reason>-<date>/` folders without manifest still work but are restored by hand.
- `import_data.py`, `sample_data.py` and the export include the history block.
- Privacy statement: one exception to "writes only inside the project folder" (`backup.py`).

## 1.2.0 – 2026-11-20

### Added

- User manual `docs/manual.md`: what the audit is for, first start, reading the overview, running an audit, decisions, day-to-day care (including adding candidates that were never installed, export and import), security and privacy, FAQ and troubleshooting, glossary.
- README: feature list and a short step-by-step guide for export and import.
- Overview page, section Usage: entries for adding a candidate, saving data (export) and bringing data along (import); the manual in the documentation table.
- `check_overview.py --help`.

### Fixed

- Getting started and review guide described two check results inaccurately (missing-file warning, `--inventory` on a page without entries).

## 1.1.0 – 2026-11-20

### Added

- `tools/import_data.py`: imports audit data from a JSON file (same shape as `examples/sample-data.json`) into a fresh download, so an existing review does not have to be repeated; `--export` writes the current page data to such a file (backup, moving to a newer download). Validates on a temporary copy first, refuses to overwrite existing data without `--replace`, never changes the input file.
- Documentation: "Moving existing data in" in Getting started and Overview structure, one line in the README.

## 1.0.3 – 2026-11-20

### Changed

- Open items are light cards with an accent edge instead of full accent-colour blocks, so they no longer outshout the page and differ from the sample notice.
- Group links above the list are a "Jump to:" row of underlined links, clearly different from the filter buttons.
- Status tags show only the word, without the dot.
- Sample notice uses a colon instead of a dash; candidate kinds read "Skill (single skill)" instead of a middle-dot chain.
- Token card values are laid out on a grid (arrow centred without computed offsets); filter buttons no longer wrap; footer text measure 72 characters; key-figure cards set their own text colour.

### Fixed

- `check_overview.py` ignores the "Jump to:" label when it checks the group links.

## 1.0.2 – 2026-11-20

### Added

- `data-tokens.first_audit_estimated`: when true, the first-audit value is labelled "estimated" / "geschätzt", otherwise "measured" / "gemessen". The sample data uses it.

### Fixed

- Token card: label, number and note of both values now sit on the same lines, and the arrow is centred on the numbers.

## 1.0.1 – 2026-11-20

### Fixed

- Big numbers in the token card and the key-figure cards rendered at label size, and the overlap legend showed two color squares per item: three style rules also matched the language spans inside the numbers and labels. They now apply to direct children only.

## 1.0.0 – 2026-11-20

### Added

- Overview page `audit-overview.html`: one self-contained, bilingual (English/German) page with key figures, open items, token card, overlaps, a searchable and filterable list of all customizations in eight groups, documentation table, glossary and usage notes. Works offline and without JavaScript.
- Python tools (standard library only): `inventory.py`, `count_usage.py`, `count_mcp_usage.py`, `check_desktop_plugin.py` (all read-only), `build_overview.py` and `check_overview.py`, `selftest.py`, plus `paths.py` for shared path logic.
- Sample data (`examples/sample-data.json`) and `tools/sample_data.py` with `load`, `remove` and `status`.
- Documentation: `docs/getting-started.md`, `docs/review-guide.md`, `docs/explanation-template.md`, `docs/overview-structure.md`, `docs/agent-briefs.md`.
- `CLAUDE.md` with working rules and a first-run routine for Claude, `DESIGN.md` with the design basis of the page.
- Stylesheet and local fonts (Roboto Slab, Roboto, JetBrains Mono) in `assets/`, with their licenses.
- Platform support: macOS full and tested; Windows `~/.claude` scanned, desktop-app folder untested; Linux `~/.claude` only.
