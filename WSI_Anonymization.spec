# Build with the yslee environment: python -m PyInstaller WSI_Anonymization.spec
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules, copy_metadata
from pathlib import Path
import PySide6
import sys

packages = ["openslide-python", "openslide-bin", "numpy", "Pillow", "tifffile", "imagecodecs", "PySide6", "shiboken6", "PySide6_Essentials"]
datas = [("logo/logo.png", "logo"), ("logo/icon.png", "logo")]
for package in packages:
    datas += copy_metadata(package)
ffi = Path(sys.prefix) / "Library" / "bin" / "ffi.dll"
extra_binaries = [(str(ffi), ".")] if ffi.is_file() else []
a = Analysis(
    ["app.py"], pathex=[],
    binaries=collect_dynamic_libs("openslide_bin") + collect_dynamic_libs("imagecodecs") + extra_binaries,
    datas=datas,
    hiddenimports=["openslide_bin"] + collect_submodules("imagecodecs"),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "matplotlib", "scipy", "pandas", "torch",
              "tensorflow", "IPython", "tkinter", "cv2", "zarr", "dask", "fsspec", "numcodecs"],
    noarchive=False,
)
# yslee's pre-existing qt.conf points QLibraryInfo at a different Conda Qt.
# Bundle plugins from the same wheel as Qt6Core/Gui/Widgets instead.
qt_root = Path(PySide6.__file__).parent
corrected = []
for destination, source, kind in a.binaries:
    relative = destination.replace("\\", "/")
    if relative.startswith("PySide6/plugins/"):
        candidate = qt_root / relative.removeprefix("PySide6/")
        if not candidate.is_file():
            continue
        source = str(candidate)
    corrected.append((destination, source, kind))
a.binaries = corrected
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="WSI_Anonymization",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False, icon="logo/icon.png")
