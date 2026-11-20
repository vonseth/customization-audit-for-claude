#!/usr/bin/env python3
"""The installed version from VERSION is shown after the h1; missing VERSION or marker is no error."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="test-build-version-")
os.environ["CUSTOMIZATION_AUDIT_HOME"] = os.path.join(TMP, "home")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
PAGE = os.path.join(TMP, "audit-overview.html")
shutil.copyfile(os.path.join(ROOT, "audit-overview.html"), PAGE)
shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(TMP, "assets"))


def build():
    r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "build_overview.py"), PAGE],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    with open(PAGE, encoding="utf-8") as f:
        return f.read()


with open(os.path.join(TMP, "VERSION"), "w", encoding="utf-8") as f:
    f.write("9.8.7\n")
html = build()
assert '<!-- AUTO:VERSION:START --> <span class="count version">9.8.7</span><!-- AUTO:VERSION:END --></h1>' in html
with open(os.path.join(TMP, "VERSION"), "w", encoding="utf-8") as f:
    f.write("<b>x</b>\n")                       # not a version: nothing is shown, nothing injected
assert "<!-- AUTO:VERSION:START --><!-- AUTO:VERSION:END -->" in build()
os.remove(os.path.join(TMP, "VERSION"))
assert "<!-- AUTO:VERSION:START --><!-- AUTO:VERSION:END -->" in build()
with open(PAGE, encoding="utf-8") as f:            # a page from before 1.4.3 without the marker still builds
    old = f.read().replace("<!-- AUTO:VERSION:START --><!-- AUTO:VERSION:END -->", "")
with open(PAGE, "w", encoding="utf-8") as f:
    f.write(old)
assert "AUTO:VERSION" not in build()
shutil.rmtree(TMP)
print("test_build_version: OK")
