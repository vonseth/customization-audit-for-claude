"""Tests for the command line of every tool: --help and -h print the usage and exit 0, and do nothing else.
Run: python3 -I tests/test_cli.py

For each tools/*.py (except paths.py and schema.py, which are not programs) the tool runs with
CUSTOMIZATION_AUDIT_HOME set to an empty temporary folder. Checked: exit code 0, non-empty stdout, and that
no file was created in the temporary home or in the repository. Bytecode writing is switched off for the
runs, so importing a module does not count as creating a file. Standard library only.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
SKIP = ("paths.py", "schema.py")
FLAGS = ("--help", "-h")


def files_below(folder):
    """Set of all file paths below folder (names only, no contents)."""
    found = set()
    for dirpath, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d != ".git"]  # git objects do not change during the runs
        for n in names:
            found.add(os.path.join(dirpath, n))
    return found


def run_tool(name, flag, home):
    env = dict(os.environ, CUSTOMIZATION_AUDIT_HOME=home, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-I", os.path.join(TOOLS, name), flag],
                          env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)


def check_tool(name, flag):
    """Returns a list of problems (empty = passed)."""
    home = tempfile.mkdtemp(prefix="cli-home-")
    try:
        before_repo = files_below(ROOT)
        before_home = files_below(home)
        try:
            p = run_tool(name, flag, home)
        except subprocess.TimeoutExpired:
            return ["timeout after 120 s"]
        problems = []
        if p.returncode != 0:
            problems.append("exit code %d (expected 0): %s" % (p.returncode, p.stderr.strip()[-300:]))
        if not p.stdout.strip():
            problems.append("stdout is empty")
        new_home = files_below(home) - before_home
        if new_home:
            problems.append("created in the temporary home: %s" % sorted(new_home)[:5])
        new_repo = files_below(ROOT) - before_repo
        if new_repo:
            problems.append("created in the repository: %s" % sorted(new_repo)[:5])
        return problems
    finally:
        shutil.rmtree(home, ignore_errors=True)


def main():
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(TOOLS, "*.py")))
    names = [n for n in names if n not in SKIP]
    failed = []
    for name in names:
        for flag in FLAGS:
            problems = check_tool(name, flag)
            if problems:
                failed.append((name, flag, problems))
    for name, flag, problems in failed:
        print("FAIL %s %s" % (name, flag))
        for x in problems:
            print("     - %s" % x)
    print("checked %d tools with %s" % (len(names), " and ".join(FLAGS)))
    if failed:
        print("test_cli: FAILED for %d run(s): %s" % (len(failed), ", ".join(sorted({f[0] for f in failed}))))
        return 1
    print("test_cli: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
