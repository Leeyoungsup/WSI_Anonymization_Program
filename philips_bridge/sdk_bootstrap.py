"""Locate native SDK DLLs inside this interpreter's environment only."""
import os
import sys
from pathlib import Path


def prime_sdk_dll_paths():
    prefix = Path(sys.prefix)
    packages = prefix / "lib" if (prefix / "python37._pth").is_file() else prefix / "Lib/site-packages"
    paths = [packages / name for name in ("pixelengine", "softwarerenderbackend", "softwarerendercontext")]
    paths += [prefix / "Library/bin", prefix / "DLLs", prefix]
    os.environ["PATH"] = os.pathsep.join(str(p) for p in paths if p.is_dir()) + os.pathsep + os.environ.get("PATH", "")
