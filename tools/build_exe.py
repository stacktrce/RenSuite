"""Build a standalone RenPySuite executable with PyInstaller.

    pip install pyinstaller
    python tools/build_exe.py            # → dist/RenPySuite.exe (Windows) or dist/RenPySuite

Use --dry-run to only print the PyInstaller command.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def command():
    assets = ROOT / "renpy_suite" / "assets"
    return [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "RenPySuite",
        "--icon", str(assets / "icon.ico"),
        "--add-data", "%s%srenpy_suite/assets" % (assets, os.pathsep),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        str(ROOT / "RenPySuite.pyw"),
    ]


def main():
    cmd = command()
    print(" ".join('"%s"' % c if " " in c else c for c in cmd))
    if "--dry-run" in sys.argv:
        return 0
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
