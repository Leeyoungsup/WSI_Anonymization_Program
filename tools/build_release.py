"""Build and package the portable Windows release. Run with requirements-build.txt."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.1.1"
NAME = "WSI_Anonymization-" + VERSION + "-Windows-x64"


def main():
    if "--package-only" not in sys.argv:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "WSI_Anonymization.spec"],
                       cwd=ROOT, check=True)
    folder = ROOT / "release" / NAME
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / "WSI_Anonymization.exe"
    shutil.copy2(ROOT / "dist" / exe.name, exe)
    shutil.copy2(ROOT / "docs" / "release_readme.txt", folder / "READ_ME.txt")
    validation = ROOT / "docs" / "release_validation.md"
    if validation.exists():
        shutil.copy2(validation, folder / "VALIDATION.md")
    pyramid_validation = ROOT / "docs" / "pyramid_tiff_validation.md"
    if pyramid_validation.exists():
        shutil.copy2(pyramid_validation, folder / pyramid_validation.name)
    packages = ["openslide-python", "openslide-bin", "numpy", "Pillow", "tifffile", "imagecodecs",
                "PySide6", "PySide6_Essentials", "shiboken6", "pyinstaller", "pyinstaller-hooks-contrib",
                "packaging", "psutil", "cffi", "pycparser", "setuptools", "pywin32", "six"]
    licenses = folder / "THIRD_PARTY_LICENSES"
    installed_packages = []
    for name in packages:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        installed_packages.append(name)
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ("license", "copying", "copyright", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file() and ".." not in file.parts:
                    target = licenses / name / file
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    # The Qt wheels' metadata does not include all open-source license texts.
    qt = licenses / "Qt"
    qt.mkdir(parents=True, exist_ok=True)
    for license_name in ("LGPL-3.0-only.txt", "GPL-3.0-only.txt", "Qt-GPL-exception-1.0.txt"):
        url = "https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/" + license_name
        with urllib.request.urlopen(url, timeout=30) as response:
            (qt / license_name).write_bytes(response.read())
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    (licenses / "SOURCES.txt").write_text(
        "OpenSlide and bundled library sources: https://github.com/openslide/openslide-bin/releases/tag/v4.0.1.2\n"
        "OpenSlide Python: https://github.com/openslide/openslide-python/tree/v1.4.6\n"
        "Qt 6.8.3: https://download.qt.io/archive/qt/6.8/6.8.3/submodules/\n"
        "PySide/Shiboken: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/\n"
        "Qt/PySide are used under their open-source license options. The accompanying source-build.zip\n"
        "contains application and build files to rebuild with replacement compatible libraries.\n"
        "Imagecodecs: https://github.com/cgohlke/imagecodecs\n", encoding="utf-8")
    source_files = [ROOT / name for name in ("app.py", "wsi_anonymizer.py", "WSI_Anonymization.spec",
                                            "requirements.txt", "requirements-build.txt")]
    source_files += sorted((ROOT / "wsi_app").glob("*.py"))
    source_files += [ROOT / "tools" / name for name in ("inspect_samples.py", "check_openslide.py", "build_release.py")]
    source_files += [ROOT / "docs" / "release_readme.txt"]
    with zipfile.ZipFile(folder / "source-build.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in source_files:
            archive.write(source, source.relative_to(ROOT))
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (folder / "BUILD_INFO.json").write_text(json.dumps({
        "version": VERSION, "platform": "Windows x64", "python": sys.version,
        "built_at_utc": datetime.now(timezone.utc).isoformat(), "exe_sha256": digest,
        "packages": {name: metadata.version(name) for name in installed_packages},
        "application_sources_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
    }, indent=2), encoding="utf-8")
    archive_path = ROOT / "release" / (NAME + ".zip")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder.parent))
    (ROOT / "release" / (NAME + ".sha256")).write_text(
        hashlib.sha256(archive_path.read_bytes()).hexdigest() + "  " + archive_path.name + "\n", encoding="ascii")
    print(archive_path)
    print("EXE bytes:", exe.stat().st_size, "ZIP bytes:", archive_path.stat().st_size)


if __name__ == "__main__":
    main()
