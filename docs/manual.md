# User manual

Customization Audit for Claude is an unofficial tool, not affiliated with Anthropic. It helps you keep your Claude customizations (plugins, skills and MCP servers) safe, lean and understandable. This manual is written for people who use Claude but do not write code. Claude does the technical work in your own session; you decide.

## Contents

1. [What it is for](#1-what-it-is-for)
2. [Installation and first start](#2-installation-and-first-start)
3. [Reading the overview](#3-reading-the-overview)
4. [Running an audit](#4-running-an-audit)
5. [Making decisions](#5-making-decisions)
6. [Day-to-day care](#6-day-to-day-care)
7. [Security and privacy](#7-security-and-privacy)
8. [FAQ and troubleshooting](#8-faq-and-troubleshooting)
9. [Glossary](#9-glossary)

The technical details live in other files. This manual summarizes them and links to them: [README](../README.md), [getting started](getting-started.md), [review guide](review-guide.md), [explanation template](explanation-template.md), [overview structure](overview-structure.md), [agent briefs](agent-briefs.md).

---

## 1. What it is for

Over time a Claude setup collects plugins, skills and connectors. Each one may be useful, but each one also costs something, and some may be risky. An audit takes stock of all of them and gives you a clear list with a recommendation for each item.

### What an audit gives you

- **Security.** Every third-party and own customization is read file by file: hooks that run by themselves, network access, reads of personal data, downloads, executed third-party code, prompt-injection patterns. Each finding gets a risk level (Critical, High, Medium, Low, Harmless) and is marked as proven or as an assumption.
- **Token cost per session.** The short descriptions of all installed customizations are read by Claude at the start of every session, whether you use them or not. That "permanent context" is counted in tokens (roughly characters divided by 3.7). You see what each item costs and the total, measured on a date. Connected MCP servers cost additional context.
- **Overlaps.** Several customizations for the same job cost context several times and can compete for a request. The audit groups them by topic, names who is responsible for what, and rates each member.
- **Usage.** Your own session history is counted: which skills, commands and MCP servers you really call, and how often.
- **Versions.** Newer versions of what you have installed are looked up, and for each one the changes are checked before you decide to update.

The result is one overview page, `audit-overview.html`, and a running report in `reports/audit-report.md`.

### What it cannot do

- It does not decide for you. Recommendations are suggestions; nothing is removed or updated without your explicit yes.
- It is not a virus scanner or a guarantee. A security review reads files and reports what it finds; it says what was not checked. "Low" is not "safe".
- It cannot look inside claude.ai connectors. They run at the provider; only their tool names and instructions are visible in a session.
- It cannot count use outside the Claude app on this computer. Use in the browser and in the phone app is not included in the usage numbers.
- It does not measure how good a customization is, only what it costs, whether it overlaps with others and whether you call it.
- Windows desktop-app data is untested; on Linux only `~/.claude` is scanned (see [section 8](#8-faq-and-troubleshooting)).

---

## 2. Installation and first start

The full walkthrough is in [getting started](getting-started.md). In short:

1. **Python.** You need Python 3.9 or newer (standard library only; nothing to install with pip). Check with `python3 --version`. On Windows the command may be `py -3 --version`.
2. **Download.** Open <https://github.com/vonseth/customization-audit-for-claude/releases/latest>, download **Source code (zip)** and unzip it somewhere you will find again. Or, if you know git: `git clone https://github.com/vonseth/customization-audit-for-claude.git`. Keep the folder: your overview page, reports and decisions live in it.
3. **Open the folder in Claude Code.** Desktop app: Code tab, then choose the folder. Command line: `cd` into the folder and run `claude`.
4. **Say hello.** Type, for example: "Start the customization audit." Claude reads `CLAUDE.md`, sees that the overview is still empty and asks you once whether you want to see the sample overview first or start the first audit.
5. **Open `audit-overview.html`** in your browser (double-click the file).

The file `VERSION` in the project folder holds the installed version; `python3 -I tools/update.py check` compares it with the latest release (see [Updating to a new version](#updating-to-a-new-version)).

### Sample data

The sample data is fictional. It fills every part of the overview so you can see what a finished audit looks like. Claude runs these commands for you, and you can run them yourself:

```text
python3 -I tools/sample_data.py load
python3 -I tools/sample_data.py status
python3 -I tools/sample_data.py remove
```

- `load` fills the page with the sample and rebuilds it. While the sample is loaded, a notice at the top says so. It refuses to run if your page already holds real data.
- `status` tells you whether sample data is loaded.
- `remove` empties the page again. It only ever removes sample data, so your own entries cannot be deleted by mistake.

**Remove the sample before your real audit**, otherwise fictional entries mix with yours.

### Importing existing data instead of a first review

If you already did an audit, for example in an earlier download of this project, you do not need to repeat the first review. Export the data from the old copy and import it into the new one:

```text
python3 -I tools/import_data.py --export my-audit.json
python3 -I tools/import_data.py ../my-audit.json
```

The first command runs in the old copy, the second in the new one (adjust the path to the file). From 1.4.0 on, `tools/update.py` does this for you for a newer version of the project itself ([section 6](#updating-to-a-new-version)); the manual path is described under [Backup and moving data](#moving-your-data-by-hand).

### Your first real audit

When the page is empty (or the sample is removed), tell Claude: "Run the audit following docs/review-guide.md." What happens then is described in [section 4](#4-running-an-audit).

---

## 3. Reading the overview

`audit-overview.html` is one self-contained file. It works offline, without JavaScript, and on a phone (for example in the Files app). There is no external resource on it. Parts of it are generated by a script from your data; the rest is fixed text. You never edit the generated parts by hand; Claude updates the data and rebuilds the page ([overview structure](overview-structure.md) explains how).

### Top of the page

- **Sample notice.** Only visible while sample data is loaded. It shows the command to remove the sample.
- **Jump bar.** A bar with five links: Open items, Tokens, Overlaps, Customizations, Help (the documentation section). On wide screens (1,024 pixels and up) it stays at the top while you scroll.
- **DE | EN toggle.** At the right end of the jump bar. The page picks English or German from your browser language; the toggle overrides that. Without JavaScript the page shows English.
- **Title and date.** "Customization Audit for Claude" with "As of" and the date of the data.

### Key figures

Six cards at the top:

1. **Plugins and skills installed** (with how many of them are disabled).
2. **claude.ai skills active** (with how many were removed).
3. **MCP servers connected** (with how many are not signed in).
4. **Not installed yet:** candidates that are still on the list.
5. **Plugins and skills removed.**
6. **Not yet discussed:** plugins, MCP servers and candidates that are still present but have not been gone through one by one with you.

### 01 Open items

One card per open point, for example "Decide on X: re-enable or remove". Finished items are deleted rather than ticked off, so this section always shows only what is still to do. On a fresh page it says "No audit yet".

### 02 Tokens per session

A dark card with the permanent context per session:

- **At first audit** and **now**, side by side, with the saving as a percentage and in tokens.
- Under each value the label **measured** or **estimated**. Your first audit is often estimated, because the measurement tool did not exist yet or was not run; later values are measured.
- A **stacked bar** that splits the total into up to four parts (for example desktop plugins, local plugins, own skills, claude.ai skills).
- A short note with the measurement date. Connected MCP servers cost additional context and are not part of the bar.
- **MCP line.** Once you have measured MCP cost (see [section 4](#4-running-an-audit)), one line says, for example: "MCP servers add ~22,580 tokens per session (measured on the date); another ~130,000 load only when needed." The first number is permanent: the MCP tools that are loaded plus the instructions the servers send. The second number is only loaded when a tool is actually needed. Without a measurement the line is not shown.
- **History.** From the second snapshot on (see [section 6](#history-of-your-audits)) a timeline appears: one row per audit with the date, the permanent tokens, the number of installed and removed items and of candidates, and a bar scaled to the highest value. With zero or one snapshot nothing is shown.

Only measured totals appear here. Per-group sums in the list are counts only, never token sums, because the per-row values are approximations.

### 03 Overlaps

Topics where several customizations do similar work. Three small cards show how many topics, how many customizations are involved, and how many tokens they cost per session (out of the total).

Each topic can be opened:

- **Responsible:** who handles which kind of request, in one or two sentences.
- **Members** with their tokens and a marker: **starts by itself** (auto-start, the description is read in every session) or **only when called** (the skill can only be started with its `/name`, so it costs almost nothing until then).
- **Role:** one member per topic is the **core** (shown as "most value"), others are **complement** (does a different job, adds to the core) or **replaceable** (the core or another item covers it; the page names by what).
- **Uniqueness:** five dots. More dots mean it does something nobody else here does.
- A short **reason**.

Roles are recommendations. Nothing is removed without going through it with you first.

### 04 Customizations

The main list of everything.

**Legend.** "What do the labels mean?" explains the tags. You can fold it away.

| Tag | Meaning |
|---|---|
| installed / connected (shown as "in use") | In place and working |
| disabled | Installed but switched off |
| not signed in | A plugin's MCP server without sign-in: not usable. It only goes away with its plugin |
| built-in | Part of Claude Code itself, not installed by you |
| not installed (candidate) | Named by you, not installed |
| removed | Uninstalled |

**Search, sort and filters.**

- **Search** looks through names and texts of all entries; groups with no match are hidden, and a collapsed group opens if it contains a match.
- **Sort:** as in the list (default), Name, Tokens (descending) or Status.
- **Filters:** All, Installed, Not installed yet, Removed, With external data (customizations that read from or send to an outside service).
- **Jump to:** a row of links, one per group.

**Groups.** The list is divided into eight groups:

| Group | Content |
|---|---|
| Your own marketplaces | Plugins from a repository you control |
| Desktop plugins | Installed in the Claude app |
| Local plugins and skills | Installed through Claude Code, plus your own skills in `~/.claude/skills` |
| claude.ai skills | Managed on claude.ai |
| MCP servers | Connectors, plugin MCPs, extensions, your own servers. Plugin MCPs without sign-in sit in a collapsed subgroup |
| Built-in | Parts of Claude Code. Listed only, not counted anywhere |
| Not installed yet | Candidates, in subgroups by kind (connector, MCP server, plugin, skill, other) |
| Removed | A collapsed archive. It opens by itself when you search or filter |

Each group shows a count next to its name. Counts only, never token sums.

**Columns in the closed row.** Name, Status (the tag), Tokens, Purpose. In candidates the third column is "Discussed" (discussed / open), and in the Removed archive the last column is "Reason / replacement".

**Details when opened.** Click or tap a row. For plugins and skills you see: source, origin, category, external data sources, usage (number of calls), overlaps with, and the recommendation. MCP servers show kind, origin, sign-in and access, usage, security notes, overlaps and the recommendation, and, if measured, **Context size (all tools)**: the tokens of all tools of that server taken together, as listed by `/context`. This is the size of the server's whole tool list, not what it permanently costs: only part of the tools may be loaded, and the others only on demand. The split per server is not available. Candidates show kind, provider, address (the link to where it comes from), overlaps and a note.

**Usage.** The count of calls in the Claude app on this computer, up to the date of the last count. "0" means no call in that time.

### 05 Documentation

A collapsible table of the files of this project with one line on each. If a file listed there does not exist yet (for example `reports/audit-report.md` before your first audit), the check script warns about it.

### 06 Glossary

A collapsible list of the terms. A copy of it, extended, is in [section 9](#9-glossary) of this manual.

### 07 Usage

A collapsible section "How do I use the audit?" with plain-language examples of what to say to Claude: get an overview, review everything again, install something new, get rid of something, check for new versions, read what happened.

### Footer

A note on the usage column, the author, the optional support link, the license and "Not affiliated with Anthropic". The candidate links and the support link are the only external links on the page.

---

## 4. Running an audit

This is what you experience. The method behind it is in the [review guide](review-guide.md).

**You say:** "Run the audit following docs/review-guide.md."

**Then Claude, without changing anything:**

1. First shows **what changed since the last audit** with `python3 -I tools/diff_inventory.py`: what is new, what is gone, what changed its status (for example disabled) and which token costs moved noticeably (at least 20 percent and 50 tokens). On a first audit it simply lists everything as new. Nothing is written.
2. Takes an **inventory** of everything installed: local plugins, your own skills and agents, desktop-app plugins, claude.ai skills, MCP servers. It writes it to `reports/inventory.tsv`.
3. Runs the **version check** for local plugins with `python3 -I tools/check_versions.py`. This works offline against the copies of the marketplaces that the app already keeps and answers "up to date", "newer available" or "unknown" per plugin. "Latest" means latest in that local copy; the tool fetches nothing. Desktop plugins and claude.ai skills have no local version source; a helper agent covers those (and whatever the tool reports as unknown).
4. Starts several **helper agents in parallel**, each read-only, each with the smallest model that fits the work: a security review, a pattern scan, a usage count, a redundancy and usefulness assessment, and the version check for desktop plugins and claude.ai skills. Their partial reports go to `reports/`. Briefs are in [agent briefs](agent-briefs.md).
5. **Measures the MCP cost** if you want the numbers (see below).
6. **Consolidates** the findings in the running report `reports/audit-report.md` (a new section "Review of <date>" each time) and fills the overview page.
7. Has an **independent agent check** the report against the raw data (the quality gate) and works in the corrections.

### Measuring the MCP cost (you run one command)

Connected MCP servers cost context in every session, but that cost cannot be read from files. It is shown by Claude Code's `/context` command, and **only you run it**; Claude never runs `/context` itself. Claude asks you to:

1. Open a **new** Claude Code session (so the number is not inflated by a long conversation).
2. Type `/context`, expand the entry **MCP tools** and copy the text (or save it to a file).
3. Paste it into the audit session, or give Claude the file.

Claude then runs `python3 -I tools/mcp_cost.py <file>` (with `--write` to store the result on the page). What is measured:

- **Permanent cost** = the MCP tools that are loaded + the instructions that the MCP servers send. This is what every session carries.
- **Deferred** = tools that are only loaded on demand. They cost nothing until used and are reported separately.
- **Per server** the tool shows the number of tools and the total tokens of all its tools. These totals **cannot be split** into loaded and deferred, because `/context` lists each tool with its size but not which of them are loaded.

Both the desktop app's copied text and the command line output are understood. Details that matter when you paste:

- **App text with one value per line** works. If your copy puts every column on its own line ("MCP tools", then "27.378", then "2,7 %"), the tool joins them again.
- **Symbols such as ®** in server names are ignored when matching.
- **Matching to your entries:** a server is matched to an entry of the same name (case, spaces and punctuation ignored). If none matches exactly, the part of an entry's name before " (" counts, for example "Linear" for "Linear (Connector)". That fallback applies only if it points to exactly one entry that is not removed (a connected one wins over one that is not signed in); otherwise the entries are listed and left unchanged.
- **Different names are not matched.** "Meetings" and "Claude Meetings" are two names. Rename the entry like the server, or set the value by hand.
- **Connector IDs:** in the command line format, claude.ai connectors appear under an ID (a long string with hyphens) instead of their name. The tool looks the names up in the connector lists the desktop app keeps in its local session files (read-only, only ID and name are taken, nothing else is shown) and prints "Connector IDs resolved from local app data: N". `--no-resolve` switches this off; IDs that cannot be found stay as they are.

The result appears in the MCP line of the token card and, per server, as "Context size (all tools)".

**Then you decide, one item at a time.** Claude goes through the customizations in a fixed structure ([explanation template](explanation-template.md)): what it is, what it contains, what it costs, whether it fits what you do, overlaps, risks, what speaks for it, and a recommendation. Security findings come first, then new versions, then the biggest context items, then the rest. After each explanation Claude waits for your answer. You can ask questions at any time.

**Only then does anything change.** Specifically:

- **Nothing changes without your OK.** Claude lists first, explains, asks, and only then acts.
- **A backup comes first.** Before every change Claude saves what it is about to change with `python3 -I tools/backup.py create <reason> <paths>` to `~/.claude/backups/<reason>-<date>/`, and checks the result afterwards. Details in [section 6](#backups-and-restore).
- **Some steps are yours.** Desktop-app plugins and claude.ai skills are removed by you in the Claude app; Claude tells you where to click and then checks that it worked ([section 5](#where-removal-happens)).
- **Effect from the next session.** Changes apply when you start a new session. Test a changed plugin in a new session.

**After every decision** Claude updates your data, rebuilds and checks the overview page, adds a line to "Changes made" in the report, and writes your decision into `CLAUDE.md`, so that nothing lives only in the chat.

**When the audit is finished,** Claude stores a snapshot of the key numbers with `python3 -I tools/history.py snapshot` ([section 6](#history-of-your-audits)).

**How long.** The inventory takes a few minutes. The parallel review phase usually takes a while longer, depending on how many customizations you have. The one-by-one discussion takes as long as you want it to; you can stop after any item and continue in another session, because everything is written down.

---

## 5. Making decisions

### The answers you can give

| For an installed item | What it means |
|---|---|
| **Keep it.** | It stays. It is noted as "kept deliberately" and is shown again only if something changes (new version, new finding, different usage). |
| **Remove it.** | It is uninstalled after a backup, and moves to the "Removed" archive with the reason. |
| **Disable it.** | Installed but switched off. It stops costing context. Reversible. |
| **Borderline** | Claude names the one question the decision hangs on, with both answers. |

| For a candidate | What it means |
|---|---|
| **Install** | Claude first runs the security and overlap review, then you install it (connectors you connect yourself in your account). After installing, the entry moves from the candidate list into the inventory. |
| **Don't install** | Claude asks: "Should the entry be removed from the list?" |
| ... **Yes** | The entry moves to the "Removed" archive, subgroup "Candidates, never installed", with the reason. |
| ... **No** | It stays under "Not installed yet", marked as discussed, with your decision noted. |

### Core, complement, replaceable

These roles come from the overlap section and are only recommendations:

- **Core:** the one customization in a topic that brings the most value. Exactly one per topic.
- **Complement:** it overlaps, but does a different job or adds something the core lacks. Keep both.
- **Replaceable:** the core (or another named item) covers what it does. This is the usual candidate for removal, but you decide.

### Where removal happens

| Kind | Who removes it | How |
|---|---|---|
| Desktop-app plugins | You | In the Claude app: Customize, then Plugins. Claude then checks with `python3 -I tools/check_desktop_plugin.py "<name>"`. |
| claude.ai skills | You | In the Claude app: Customize, then Skills. Claude then checks the same way. |
| Local Claude Code plugins | Claude | With the `claude plugin` command (`claude plugin uninstall <name>@<marketplace>` or `claude plugin disable <name>@<marketplace>`), after your OK and a backup. |
| Your own skills | Claude | After a backup, by deleting the folder in `~/.claude/skills/`. |
| claude.ai connectors | You | In your account's connector list ("Disconnect"). |

If you ask for short feedback after removing a desktop plugin or claude.ai skill, Claude answers with exactly "Yes, it was removed." or "No, it was not removed." and nothing else.

Things to keep in mind:

- **A plugin is not a connector.** A claude.ai connector is independent of a plugin with the same name. Removing one does not touch the other.
- **Display names in the app can differ** from the plugin's own name. Claude matches by the manifest, not only by the label.
- **Never uninstall Claude Code with Homebrew's `--zap`.** It deletes `~/.claude.json`, which holds your account and connectors.
- **Clicking through the app can install a plugin by accident.** Check the plugin list after a removal.

---

## 6. Day-to-day care

### When to re-check

Run the audit again every few months, in the same scope and form. Say: "Run the audit following docs/review-guide.md." Each run adds a new section to the running report, includes a version check, and shows items you already decided on only if something changed. Do a short check whenever you install several things at once, or when your sessions suddenly feel slower or more crowded.

Check for new versions at any time: "Are there new versions of my customizations?" Claude runs the offline check for local plugins (`check_versions.py`), looks at desktop plugins and claude.ai skills separately, names what changed and updates only when you ask. "What changed since the last audit?" runs `diff_inventory.py`.

### History of your audits

At the end of every audit Claude stores a **snapshot**: the date, the permanent tokens, how many plugins and skills are installed and removed and how many candidates are on the list. Say "Store a snapshot of this audit" or let Claude do it as the last step:

```text
python3 -I tools/history.py snapshot
python3 -I tools/history.py list
```

A second snapshot on the same date is refused unless you add `--replace`; a date before the latest snapshot is refused. From two snapshots on the token card shows the timeline, so you can see whether your setup grows or shrinks over time. Take the snapshot only when the numbers of the page are final.

### Backups and restore

Before every change Claude makes a backup with `backup.py`:

```text
python3 -I tools/backup.py create <reason> <path> [<path> ...]
python3 -I tools/backup.py list
python3 -I tools/backup.py show <folder-name>
python3 -I tools/backup.py restore <folder-name>
```

- **create** copies the files or folders into `~/.claude/backups/<reason>-<date>/` and writes a `manifest.json` there: the original path of each item, the stored copy, the type, a checksum and the size. The reason uses lowercase letters, digits and hyphens.
- **list** and **show** tell you what exists and what a backup holds. Backups made before version 1.3.0 have no manifest; they are listed as "no manifest (restore by hand)". They are still valid copies, but you or Claude have to copy the files back yourself.
- **restore** first prints what would be written or overwritten (and which originals differ from the backup), then asks "Restore these N items? [y/N]". **Only "y" or "yes" proceeds.** Claude does not answer that question for you; it comes to you. Before anything is overwritten the current files are saved in a safety backup with the reason `before-restore`, and afterwards the checksums of the restored files are verified. Before anything is written, the stored files are checked against the manifest checksums; a damaged backup is refused. Nothing is deleted; files that are not in the manifest stay as they are. A manifest that points outside your home folder (symlinks are resolved) is refused.

This is the only place where a tool of this project writes outside the project folder ([section 7](#7-security-and-privacy)).

### Installing something new

Say: "I want to install the plugin XY, please check it" and add the link. Claude explains benefit, cost and risks and gives a recommendation. Only after your yes do the security check and the installation follow. Afterwards the overview is updated.

### Adding candidates that were never installed

A **candidate** is something you are only considering: a connector, MCP server, plugin or skill you have seen somewhere and have not installed. The audit can keep a list of them so you can compare them with what you already have before you decide.

**How to add one.** Tell Claude, for example:

```text
Add the connector X as a candidate: https://example.com/x
```

You can add several at once as a list:

```text
Add these as candidates:
- Connector A: https://example.com/a
- Skill B: https://example.com/b
```

**What Claude does.** It researches what the thing is (its kind), who provides it, what it is for, and what it overlaps with in your setup. It adds an entry to the data block `data-candidates` of the overview, builds the page and runs the check. **It installs nothing.** Candidates are only researched, not security-reviewed.

**Where it appears.** In the group "Not installed yet", in the subgroup for its kind, and it counts as "not yet discussed" in the key figures until you have discussed it. The address you gave is shown as a link in the details; that link is one of the few external links on the page.

**Discussing it.** Ask Claude to go through it. It uses the same fixed structure as for installed items ([explanation template](explanation-template.md)) and ends with two answers: **Don't install** and **Install**, with the one matching the recommendation first. Then:

- **Install:** the security and overlap review of the [review guide](review-guide.md) comes first, then you install it. The entry then moves from the candidate list into the inventory (plugins and skills, or MCP servers).
- **Don't install**, and Claude asks whether the entry should be removed from the list:
  - **Yes:** the entry is marked as discussed and moves to the archive "Removed", subgroup "Candidates, never installed", with the reason in the last column.
  - **No:** the entry stays under "Not installed yet", marked as discussed.

**The data block, for those who want to look.** One entry in `data-candidates` needs only three keys: `name`, `kind` and `url`. For example:

```json
{
  "name": "acme-wiki-connector",
  "kind": "connector",
  "url": "https://example.com/acme-wiki"
}
```

Allowed values for `kind`: `connector`, `mcp-server`, `plugin`, `skill`, `other`. The address must start with `https://`. Optional keys: `kind_detail`, `provider`, `purpose`, `overlaps_with`, `note`, `discussed` (true or false, default false) and `removal_reason`. A candidate with a non-empty `removal_reason` moves to the archive. Text fields can be plain text or an object with `en` and `de` texts. The full list is in the docstring of `tools/build_overview.py` and in the [overview structure](overview-structure.md). Normally you do not edit this yourself; Claude does.

### Updating to a new version

Copies of version 1.3.0 or older do not contain `update.py` yet. For the first move to 1.4.0, download 1.4.0 and use the manual path (export in the old copy, import in the new one, then copy `reports/` and your `CLAUDE.md` decisions by hand). From 1.4.0 on, `update.py` does this for you.

`tools/update.py` brings your copy to the newest release without losing your data. Run it only when you want to update; Claude runs it only on your request and never answers its confirmation question for you.

```text
python3 -I tools/update.py check
python3 -I tools/update.py apply
```

- **`check`** reads the file `VERSION`, asks GitHub for the latest release of this project and prints the installed and the latest version and the release notes. If you are offline or GitHub does not answer, it says so calmly and changes nothing.
- **`apply`** downloads the latest release and shows a preview: which managed files are replaced, added or removed, what is kept, and which extra files of yours it found. You confirm with "y". Then it makes a **full backup** of the project folder (with `backup.py`, reason `before-update-<old>-to-<new>`), replaces the managed files, carries over your page data (migrated to the current data format) and your `CLAUDE.md` sections, builds the page and runs the checks and the self-test. If anything fails, the backup is restored automatically. The name of the backup is written to `.update-state.json`.
- **Offline:** download the release ZIP in a browser and run `python3 -I tools/update.py apply <release.zip>`. No network is used.
- **`rollback`** restores the project folder from the backup of the last update, after a confirmation and a safety backup of the current state. Files created since the update are removed, so reports and data created since the update are reverted too.
- **Git users:** an update refuses to run in a git checkout. Run `git pull`, then `python3 -I tools/update.py migrate`. It only migrates the data format of the page and adds the markers to `CLAUDE.md`; no files are replaced. It backs up those two files first.
- **Private repository:** set the environment variable `GITHUB_TOKEN` to a token that can read the repository. It is sent only to api.github.com and never printed. Without it, a private repository answers "not found".

**What is replaced** (managed files): `tools/`, `tests/`, `assets/`, `docs/`, `examples/`, `README.md`, `LICENSE`, `CHANGELOG.md`, `DESIGN.md`, `VERSION`, `.gitignore`, the generated parts of `audit-overview.html` and the rules part of `CLAUDE.md`.

**What is kept:** your reports in `reports/`; all data blocks of the overview page; the sections of `CLAUDE.md` between `<!-- USER:START name -->` and `<!-- USER:END name -->` (your decisions and the status); and every extra file outside the managed folders. Only text between the USER markers in `CLAUDE.md` is kept; put your own additions there. Text outside the markers is replaced.

**Warning:** extra files you added *inside* the managed folders (`tools/`, `tests/`, `assets/`, `docs/`, `examples/`) are removed by an update. They appear in the preview under "removed" and are in the backup, so nothing is lost for good. Keep your own files elsewhere.

A downgrade is refused unless you add `--allow-downgrade`. A ZIP that is not a release of this project is refused.

### Backup and moving data

Your audit data lives in the data blocks at the end of `audit-overview.html`. A JSON export is both a backup and a way to move your data by hand. From 1.4.0 on, prefer `update.py` to move to a newer version of the project (above).

#### Moving your data by hand

1. **In the old copy**, write the data out:

   ```text
   python3 -I tools/import_data.py --export my-audit.json
   ```

   This creates the file `my-audit.json` with one key per data block. The file contains your own data. Keep it out of any public repository.
2. **Download and unzip the new version** (see [section 2](#2-installation-and-first-start)) and move or copy `my-audit.json` where you can reach it, for example next to the new folder.
3. **In the new copy**, import it:

   ```text
   python3 -I tools/import_data.py ../my-audit.json
   ```

   The import checks the file against the schema first, in a temporary copy of the page. If anything is wrong, it reports the error and changes nothing. Then it writes the blocks and builds the page.
4. **Check the page:**

   ```text
   python3 -I tools/check_overview.py
   ```

5. **Copy by hand** what is not part of the file: your reports in `reports/`, your decisions and status (paste them into the sections between the `USER:START` and `USER:END` markers of the new `CLAUDE.md`), and `assets/` if you changed anything there.

If the page in the new copy already holds data (the sample or your own), the import refuses and tells you so. Add `--replace` to overwrite it, for example to replace the sample:

```text
python3 -I tools/import_data.py ../my-audit.json --replace
```

The import file is never modified. Exporting and importing again gives a byte-identical page.

---

## 7. Security and privacy

- **What the tools read.** Only local files: `~/.claude` (plugins, settings, your skills and agents, session transcripts, history) and the Claude desktop app's data folder (plugin lists, claude.ai skills). The usage counters read your transcripts and report names and numbers only, never the contents.
- **What they write.** Inside this project folder only, with one exception. The inventory, counters, `diff_inventory.py` and `check_versions.py` only read; the build script, `tools/sample_data.py`, `tools/import_data.py`, `tools/history.py` and `tools/mcp_cost.py --write` write only the overview page; the optional output file of the inventory goes where you tell it. **The exception is `tools/backup.py`** (which `update.py` also calls for its full backup before an update; `update.py` itself writes only inside the project folder)**:** it writes backups to `~/.claude/backups/` and, when you restore a backup and confirm, to the original paths listed in that backup's manifest. It never deletes your files (it only removes its own unfinished backup folder after a failed create) and refuses manifests that point outside your home folder.
- **Your own `/context` output.** `mcp_cost.py` reads the text you give it. It never starts Claude and never reads `~/.claude`. Only to turn connector IDs into names does it read, without changing anything, the connector lists in the session files of the desktop app (`claude-code-sessions`); it takes nothing but ID and name from them. `--no-resolve` skips this.
- **Network.** Only `tools/update.py` uses the network, and only when you run `check` or `apply` without a ZIP file: read-only GET requests to api.github.com for the latest release of this project and the download of that release. Nothing is uploaded. A `GITHUB_TOKEN` (private repositories) goes only to api.github.com. All other tools use no network. The overview page has no external resources; its stylesheet and fonts are embedded.
- **Backups.** Before every change Claude saves what it is about to change to `~/.claude/backups/<reason>-<date>/` on your computer. A restore overwrites files only after your explicit confirmation.
- **Nothing is sent to third parties by this project.** The reports and the overview stay on your computer; what you share is up to you. Note that the audit runs in your own Claude session as usual, so what Claude reads in a session is processed like any other session content.
- **Your data in files.** Reports, the export file and `CLAUDE.md` decisions may contain names of your customizations and notes about your work. Do not publish them without looking.
- **Untrusted content stays data.** In the review phases, text found in repositories or on web pages is treated as data, not as instructions to the agent.
- **No change without your yes,** and removals of desktop-app plugins and claude.ai skills are done by you in the app, not by Claude.

---

## 8. FAQ and troubleshooting

**1. `python3: command not found`.**
Python is not installed or not on your path. Install it from <https://www.python.org/downloads/> (macOS also with `brew install python`; Linux with your package manager, for example `sudo apt install python3`). On Windows tick "Add python.exe to PATH" in the installer, or use the `py -3` launcher instead of `python3`.

**2. What does `-I` in the commands mean?**
It starts Python in isolated mode, so stray files in the folder cannot be loaded by accident. Keep it.

**3. The page shows English, but I want German (or the other way round).**
The page follows your browser language. Use the DE | EN toggle at the right end of the jump bar. Without JavaScript the page always shows English.

**4. A notice at the top says "Sample data". Is this my data?**
No. It is fictional data. Remove it with `python3 -I tools/sample_data.py remove`. `python3 -I tools/sample_data.py status` shows whether it is loaded.

**5. `sample_data.py load` refuses to run.**
Your page already holds real data. The sample tool never overwrites it. That is deliberate.

**6. My desktop-app plugins and claude.ai skills are not listed on Linux.**
That is expected. On Linux only `~/.claude` is scanned; there is no official source for the desktop-app data folder.

**7. Desktop-app data is not found on Windows.**
The folder location comes from the official documentation but is untested. The tools skip missing folders with a note and continue. Tell Claude what you see.

**8. The import refuses to run.**
`python3 -I tools/import_data.py <file.json>` refuses while the page holds data, sample or your own, so nothing is overwritten by accident. Save the current data first with `python3 -I tools/import_data.py --export backup.json`, then add `--replace` if you really want to overwrite.

**9. The import reports a schema error.**
The file is checked first in a temporary copy, so your page is untouched. The message names the problem (for example an unknown key, a missing required key, or a value that is not allowed). The expected shape is that of `examples/sample-data.json`: one key per block (`meta`, `plugins`, `claudeai-skills`, `mcp`, `builtin`, `candidates`, `overlaps`, `open-items`, `tokens`); a missing block counts as empty.

**10. `check_overview.py` fails with `--inventory` on a fresh page.**
Expected. With `--inventory reports/inventory.tsv` the check compares the page with your real inventory, and an installed customization missing from the page is a failure. It passes once every installed item is recorded on the page. Also make sure the inventory file was written by `python3 -I tools/inventory.py reports/inventory.tsv`; any other file is rejected.

**11. `check_overview.py` warns about a missing file.**
Files such as `reports/audit-report.md` appear during your first audit. With `--strict` such warnings become failures. Use `--strict` when you consider an audit finished.

**12. The page looks unstyled or a font is missing.**
Run `python3 -I tools/build_overview.py`. It re-embeds `assets/style.css` and the fonts. A missing font file is reported as a warning.

**13. The numbers in the key figures look wrong after I edited a data block by hand.**
Run `python3 -I tools/build_overview.py`, then `python3 -I tools/check_overview.py`. The build stops with "ERROR: ..." and leaves the file unchanged if the data are invalid. Tell Claude rather than editing by hand where you can.

**14. A removed desktop plugin is still listed.**
Ask Claude to check with `python3 -I tools/check_desktop_plugin.py "<name>"`. It answers "Yes, it was removed." or "No, it was not removed." Called without a name, it lists all desktop plugins. The app may need a moment or a restart to update its list.

**15. The audit says a hook was found in a plugin that has none.**
`tools/inventory.py` counts hooks by text search, so hits in reference texts are false alarms. Claude checks such hits itself before reporting them.

**16. Why does the usage column show 0 for something I use?**
Only calls in the Claude app on this computer are counted, up to the date of the last count. Use in the browser and the phone app is not included.

**17. A changed plugin does not seem to change anything.**
Changes apply from the next session. Start a new session and test there.

**18. Can I check that the tools themselves work?**
Yes: `python3 -I tools/selftest.py` builds a fake home folder in a temporary location, runs every tool against it and removes it again. It prints "selftest passed" if everything works.

**19. `check_versions.py` says "unknown" for a plugin.**
The tool works offline and only knows what the local marketplace copy tells it. "Unknown" appears when the plugin comes from an external source (not a relative path in the marketplace), when there is no version field and no usable git history in the copy, or when the installed commit is not in the copy. The reason is printed next to the plugin. It does not mean the plugin is outdated or broken; Claude checks those few by hand or leaves them out of the version report.

**20. `diff_inventory.py` reports a token change, but I changed nothing.**
Often it is only a different measurement. The page may hold a number measured another way (for example from `/context`) or an older estimate, while the inventory estimates characters divided by 3.7. A change is only reported if it is at least 20 percent of the page value and at least 50 tokens. Compare the reason with what you did; if nothing was updated, ignore it or raise the limit with `--threshold`.

**21. Restore asks me for a confirmation. Is that normal?**
Yes, on purpose. `backup.py restore` shows what would be written or overwritten, then asks "Restore these N items? [y/N]" and continues only on "y" or "yes". Nothing is restored on any other answer. Before overwriting, it saves the current state as `before-restore`, so even a restore can be undone.

**22. `backup.py list` shows folders marked "no manifest".**
Those are backups from before version 1.3.0. The files are intact, but a restore must be done by hand: copy the files back to their original locations. New backups always carry a manifest.

**23. `mcp_cost.py` finds no MCP lines.**
The pasted text was probably not the `/context` output, or the MCP part was collapsed. Open `/context` in a new session, expand "MCP tools", copy everything again and pass the file or the text. The tool understands the desktop app's copied text and the command line format.

**24. Why is the MCP "Context size (all tools)" larger than what the token card says?**
The token card's MCP line counts only what is permanent: loaded tools plus server instructions. "Context size (all tools)" adds up every tool of that server, including tools that are only loaded on demand. `/context` does not say which tools of a server are loaded, so the two numbers cannot be reconciled per server.

**25. Can Claude run `/context` for me?**
No. You run it in a Claude Code session and hand over the text. That keeps the measurement in your control and the tool free of any access to your Claude installation.

**26. `update.py check` says I seem to be offline.**
The tool could not reach api.github.com (no network, a proxy or firewall, or GitHub is down). Nothing was changed. Try again later, or download the release ZIP in a browser and run `python3 -I tools/update.py apply <release.zip>`.

**27. `update.py check` reports "not found" (404) for the repository.**
If the repository is private, GitHub answers 404 without a token. Set the environment variable `GITHUB_TOKEN` to a token that can read it, then run the command again.

**28. I edited a documentation file and the update replaced it.**
Files in the managed folders (and `README.md`, `CHANGELOG.md` and so on) are replaced on purpose. Your copy is in the backup named in the output (and in `.update-state.json`), under `~/.claude/backups/`. Put your own notes into your `CLAUDE.md` sections between the USER markers or into files outside the managed folders; those survive.

**29. How do I undo an update?**
Run `python3 -I tools/update.py rollback`. It shows what will be restored, asks for confirmation, makes a safety backup of the current state first and restores the project folder from the backup of the last update.

**30. "The data has schema version N, but these tools only know up to M".**
Your page data was written by a newer version of the tools than the one you are running (for example after copying a page from a newer copy). Update the tools first with `python3 -I tools/update.py check` and `apply`; do not edit the number by hand.

**31. `mcp_cost.py` did not set the value on my entry, or shows an ID instead of a name.**
The name must match the server (see "Details that matter when you paste" in [section 4](#4-running-an-audit)): "Meetings" does not match "Claude Meetings", and "Linear" for "Linear (Connector)" only works if that is the only fitting entry that is not removed. Rename the entry like the server or set the value by hand. An ID instead of a name means the desktop app's local data does not know that connector, or you used `--no-resolve`; the same fix applies.

---

## 9. Glossary

| Term | Meaning |
|---|---|
| Customization | Umbrella term for everything that extends Claude: plugins, skills, MCP servers. |
| Plugin | Package of skills, commands, agents, hooks or MCP servers. |
| Desktop plugin | Installed in the Claude app (Customize, then Plugins). |
| Local plugin | Installed through Claude Code; lives in `~/.claude/plugins`. |
| Own skill | A skill without a plugin in `~/.claude/skills`. |
| Marketplace | A source plugins are installed from. |
| Own marketplace | Your own repository that is also the marketplace of the plugin it contains. |
| claude.ai skill | Managed on claude.ai under Customize, then Skills; also appears in the desktop app and in code sessions. |
| Built-in | Comes with Claude Code (identifier `@builtin`); not installed by you, not part of the audit. |
| Candidate | A customization you named but have not installed; researched only, to be reviewed before installing. |
| MCP server | Interface (Model Context Protocol) through which Claude uses the tools of a service. |
| Connector | An MCP server from claude.ai; independent of a plugin with the same name. |
| Plugin MCP | An MCP server that a plugin brings along; it only goes away with the plugin. "Not signed in" means: not usable. |
| Extension | Desktop extension of the Claude app with its own MCP server. |
| Hook | A script that Claude Code runs automatically on an event, for example at every session start; relevant for security. |
| Auto-start blocked | A skill with `disable-model-invocation`: it only starts when you call it with `/name`. |
| Finding | A numbered single result of a partial report. |
| Tokens | Permanent cost per session caused by the descriptions (characters divided by 3.7, estimated); the content is added when a customization is called. |
| Permanent context | What Claude reads at the start of every session about your customizations (short descriptions, tool names, instructions). It costs tokens whether you use them or not. |
| Core / complement / replaceable | The roles in an overlap topic: the one with most value, one that adds a different job, one that another item already covers. |
| Uniqueness | A rating of one to five dots for how much a customization does that no other one here does. |
| Quality gate | The independent check at the end of an audit: a separate agent compares the report with the raw data. |
| Sub-agent | A helper agent Claude starts for one part of the audit, with the smallest model that fits the work. |
| Backup | A copy of what is about to change, in `~/.claude/backups/<reason>-<date>/`, made before every change with `backup.py`. |
| Manifest | The file `manifest.json` in a backup folder: original path, stored copy, type, checksum and size of every item. Restore uses it; older backups have none. |
| Snapshot | One entry in the history of your audits: date, permanent tokens, installed, removed and candidates. Stored by `history.py` at the end of an audit. |
| Deferred | Tools that are not loaded at the start of a session but only when needed. They cost no permanent context until used; `/context` reports them separately. |
| Schema version | The data format of the page data, stored as `schema_version` in the block `data-meta`. A missing value means schema 0 (data from versions before 1.4.0). Update, import and `migrate` bring the data to the format the tools expect. |
| Managed files | The files an update replaces: the tool, test, asset, documentation and example folders, the top-level project files and the rules part of `CLAUDE.md`. Your reports, page data and USER sections are not managed. |
| USER markers | The lines `<!-- USER:START name -->` and `<!-- USER:END name -->` in `CLAUDE.md`. What stands between them is yours; an update carries it over unchanged. Text outside the markers is replaced. |
| Data block | The JSON text at the end of `audit-overview.html` that holds your data; the visible page is built from it. |
| Sample data | Fictional entries that fill the page so you can see how an audit looks; removable. |
