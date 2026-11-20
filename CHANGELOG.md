# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
