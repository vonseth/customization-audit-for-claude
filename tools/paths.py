"""Shared path logic for the customization audit tools (standard library only).

Not meant to be run directly. The tools import it after inserting their own
directory into sys.path (needed because `python3 -I` removes the script
directory from sys.path).

Home directory:
  - If the environment variable CUSTOMIZATION_AUDIT_HOME is set, it replaces the
    user's home directory (useful for testing with a fake home).
  - Otherwise the home directory is taken from the environment (Path.home()).

Layout support, honestly tiered:
  - ~/.claude/ (installed_plugins.json, settings.json, skills/, agents/,
    projects/ transcripts, history.jsonl) has the same layout on all operating
    systems. Supported everywhere.
  - Claude desktop app data folder:
      macOS    ~/Library/Application Support/Claude          (tested)
      Windows  %APPDATA%\\Claude, or for the installer downloaded from Anthropic
               %LOCALAPPDATA%\\Packages\\Claude_pzs8sxrjxfjjc\\LocalCache\\Roaming\\Claude
               (UNTESTED; the folder locations are documented at
               https://code.claude.com/docs/en/hipaa-setup#code-tab-data ; the
               layout inside the folder is assumed to match macOS)
      Linux    no official source found, desktop-app data is NOT scanned.
"""
import os
import sys
from pathlib import Path

ENV_HOME = "CUSTOMIZATION_AUDIT_HOME"


def home():
    """Return the home directory (CUSTOMIZATION_AUDIT_HOME overrides it)."""
    override = os.environ.get(ENV_HOME)
    return Path(override) if override else Path.home()


def claude_dir():
    """Return ~/.claude (same layout on every OS)."""
    return home() / ".claude"


def note(msg):
    """Print a short note to stderr."""
    print("note: " + msg, file=sys.stderr)


def desktop_data_dirs():
    """Return (list of existing desktop-app data folders, note or None).

    The note explains why nothing is scanned (unsupported OS or no folder).
    """
    h = home()
    override = bool(os.environ.get(ENV_HOME))
    if sys.platform == "darwin":
        cands = [h / "Library" / "Application Support" / "Claude"]
    elif sys.platform in ("win32", "cygwin"):
        # untested; source: https://code.claude.com/docs/en/hipaa-setup#code-tab-data
        if override:
            appdata = h / "AppData" / "Roaming"
            local = h / "AppData" / "Local"
        else:
            appdata = Path(os.environ.get("APPDATA") or h / "AppData" / "Roaming")
            local = Path(os.environ.get("LOCALAPPDATA") or h / "AppData" / "Local")
        cands = [appdata / "Claude",
                 local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude"]
    else:
        return [], ("desktop-app data is not scanned on this OS (%s): no official "
                    "documentation of its location was found" % sys.platform)
    found = [c for c in cands if c.is_dir()]
    if not found:
        return [], "no Claude desktop app data folder found (looked in: %s)" % ", ".join(map(str, cands))
    return found, None


def sessions_roots(data_dirs):
    """Return the local-agent-mode-sessions folders below the given data folders."""
    return [d / "local-agent-mode-sessions" for d in data_dirs
            if (d / "local-agent-mode-sessions").is_dir()]


def short(org_id):
    """Shortened organization id (first 8 characters)."""
    return str(org_id)[:8]
