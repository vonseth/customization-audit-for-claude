# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
