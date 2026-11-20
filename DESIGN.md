# Design of the overview page

## Purpose

A calm, readable inventory. The page is meant to be read, not operated: you should grasp the state of your setup in a minute and find any single entry in a few seconds. It is one HTML file that works **without JavaScript** and **offline** (also in a phone's file viewer). The script only adds convenience: search, filters, sorting, the DE | EN toggle.

The source of the design is `assets/style.css`; `tools/build_overview.py` embeds it, with the fonts, into the page. Change the stylesheet there, then rebuild.

## Colors

Defined as variables in `:root`, with dark values under `prefers-color-scheme: dark`.

| Role | Light | Dark |
|---|---|---|
| Canvas (page) | `#f4f6f8` | `#0f1418` |
| Card | `#ffffff` | `#172026` |
| Hairline | `#d9dee4` | `#2a353e` |
| Active tab | `#e6ebf0` | `#222d35` |
| Dark surface (token card, footer) | `#17202a` | `#0a0e11` |
| Text strong (`--ink`) | `#17202a` | `#e6ebef` |
| Text (`--body`) | `#2b3540` | `#c9d2da` |
| Text muted | `#56616c` | `#9aa6b1` |
| Accent and links | `#0e6378` | `#6cc3d6` |
| Callout (open items, sample notice) | `#0e6378` with white text | the same |
| Tag installed | `#e3f1e7` on `#1f5f35` | `#183a26` on `#9fdcb4` |
| Tag disabled | `#f6edd2` on `#6b4f00` | `#3a3014` on `#f0d48a` |
| Tag removed | `#f6e1e1` on `#7f2a2a` | `#3d1d1d` on `#f2b1b1` |
| Tag info / built-in | `#e9edf1` on `#2b3540` | `#222d35` on `#c9d2da` |
| Candidates | outline only, no fill | outline only |

Status dots (decorative): installed `#2f8f57`, disabled `#b58900`, removed `#b04646`, info `#0e6378`, planned `#7b8791` (lighter variants in dark mode). The token card stack uses four accents (`#6cc3d6`, `#9fdcb4`, `#f0d48a`, `#c9b3ec`). Color never carries meaning alone: every status also has a word.

## Typography

| Use | Font | Weights |
|---|---|---|
| Headings, big numbers | Roboto Slab | 300 (h1, h2, key figures), 400 (h3, h4) |
| Text, tags, controls | Roboto | 400, 500 |
| Code, file names | JetBrains Mono | 400 |

All three are local woff2 files in `assets/fonts/` (Roboto Slab: Apache License 2.0; Roboto and JetBrains Mono: SIL Open Font License 1.1; license files next to them), embedded into the page as data URLs. System fonts are the fallback if a file is missing.

Sizes: h1 64 px (32 on phones), h2 48 px (28), h3 28 px, h4 20 px; text 14 px at line height 1.55; intros 16 px; section labels 12 px uppercase with wide letter spacing; table heads 13 px. Headings use slightly negative letter spacing and balanced line breaks.

## Spacing and shape

A 4 px grid: 8, 12, 16, 24, 32, 48 px, and 96 px between sections (48 px on phones) with a hairline on top. Radii 6, 8 and 12 px; pills fully rounded. Content is at most 1,200 px wide, with a 16 px side gutter on phones and no horizontal page scroll.

## Components

- **Key figure cards:** big slab number, short label; 3 columns, 2 on tablets, 1 on phones.
- **Tags:** pills with a status dot and a word (installed, disabled, removed, built-in); candidates are outline only.
- **Filters and search:** pill-shaped filter buttons with a pressed state, a text input (16 px so phones do not zoom), a sort menu.
- **Token card:** a dark card with "first audit" and "now" values, the saving, a stacked bar of up to four parts and a legend.
- **Entries and groups:** each customization is a collapsible row (name, tag, tokens, purpose); groups have a heading with a count. Archives, the "not signed in" subgroup, the legend and the documentation sections are collapsible.
- **Jump bar:** five entries (Open items, Tokens, Overlaps, Customizations, Help) and the DE | EN toggle; sticky from 1,024 px wide while scrolling.
- **Group chips:** small pill links above the list that jump to a group.
- **Callouts:** open items and the sample notice on the accent color.
- **Overlap topics:** collapsible cards with a bar (one segment per member) and, when open, a table with role and a five-box uniqueness rating.

## Accessibility

- Text contrast is at least 4.5 : 1 against its background in light and dark mode; muted gray is not used on cards where it would fall below that.
- Focus is always visible (2 px outline, offset).
- Touch targets in the bar and the filters are at least 40 px high.
- The page is complete without JavaScript: everything is in the HTML, English is the fallback language, the script only reveals controls that need it.
- The page follows the system color scheme and the browser language.
- Below 1,024 px, list rows stack as cards instead of columns.

## Rules

- **No external resources:** no remote fonts, scripts, images, stylesheets or network calls. The only external links are the candidates' addresses and the support link.
- **No double hairlines:** the last row of a table or list at the end of a section has no line, because the line of the next section follows.
- **No chains of middle dots** (more than one "·" in a line); use separate lines or a semicolon.
- Counts only as subtotals per group; token totals only as measured values.
- Keep descriptive texts as short as the reader needs them.
