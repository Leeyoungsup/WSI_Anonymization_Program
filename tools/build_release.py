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
VERSION = "1.10.1"
NAME = "WSI_Anonymization-" + VERSION + "-Windows-x64-Research"


def main():
    if "--package-only" not in sys.argv:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "WSI_Anonymization.spec"],
                       cwd=ROOT, check=True)
    folder = ROOT / "release" / NAME
    folder.mkdir(parents=True, exist_ok=True)
    runtime = ROOT / "build/philips_runtime"
    if not (runtime / "RUNTIME.json").is_file():
        raise FileNotFoundError("Build tools/build_philips_runtime.py before packaging this internal research release")
    runtime_info = json.loads((runtime / "RUNTIME.json").read_text(encoding="utf-8"))
    for name, expected in runtime_info["files_sha256"].items():
        if hashlib.sha256((runtime / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Philips runtime file changed: " + name)
    for source in (ROOT / "philips_bridge").glob("*.py"):
        if source.read_bytes() != (runtime / "bridge" / source.name).read_bytes():
            raise ValueError("Rebuild the Philips runtime after bridge source changes")
    shutil.copytree(runtime, folder / "philips", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(runtime, ROOT / "dist/philips", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    exe = folder / "WSI_Anonymization.exe"
    shutil.copy2(ROOT / "dist" / exe.name, exe)
    shutil.copy2(ROOT / "docs" / "release_readme.txt", folder / "READ_ME.txt")
    shutil.copy2(ROOT / "docs" / "philips_support.md", folder / "PHILIPS.md")
    shutil.copy2(ROOT / "docs" / "native_philips.md", folder / "NATIVE_PHILIPS.md")
    shutil.copy2(ROOT / "docs" / "storage_modes.md", folder / "STORAGE_MODES.md")
    shutil.copy2(ROOT / "docs" / "native_svs_ndpi.md", folder / "NATIVE_SVS_NDPI.md")
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
    # This build-owned directory is regenerated; validate its absolute boundary
    # before removing it. Long source license paths must never reach the staging
    # directory either, not just the final ZIP.
    if licenses.exists():
        resolved = licenses.resolve()
        if licenses.is_symlink() or resolved.parent != folder.resolve() or not resolved.is_relative_to((ROOT / "release").resolve()):
            raise ValueError("Unexpected release license directory")
        shutil.rmtree(("\\\\?\\" + str(resolved)) if sys.platform == "win32" else resolved)
    license_sources = {}
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
                    short = f"{len(license_sources) + 1:04d}.txt"
                    license_sources[short] = {"package": name, "original_path": str(file)}
                    target = licenses / short
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    (licenses / "ORIGINAL_PATHS.json").write_text(json.dumps(license_sources, indent=2), encoding="utf-8")
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
    source_files += sorted((ROOT / "philips_bridge").glob("*.py"))
    source_files += [ROOT / "docs" / "philips_support.md", ROOT / "requirements-philips.txt"]
    source_files += [ROOT / "docs" / "native_philips.md"]
    source_files += [ROOT / "docs" / "storage_modes.md"]
    source_files += [ROOT / "docs" / "native_svs_ndpi.md"]
    source_files += [ROOT / "tools" / name for name in ("inspect_samples.py", "check_openslide.py", "build_release.py", "build_philips_runtime.py")]
    source_files += [ROOT / "docs" / "release_readme.txt"]
    source_files += [ROOT / "logo" / name for name in ("logo.png", "icon.png")]
    with zipfile.ZipFile(folder / "source-build.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in source_files:
            archive.write(source, source.relative_to(ROOT))
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    (folder / "BUILD_INFO.json").write_text(json.dumps({
        "version": VERSION, "platform": "Windows x64", "python": sys.version,
        "built_at_utc": datetime.now(timezone.utc).isoformat(), "exe_sha256": digest,
        "philips_runtime": runtime_info,
        "packages": {name: metadata.version(name) for name in installed_packages},
        "application_sources_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
    }, indent=2), encoding="utf-8")
    archive_path = ROOT / "release" / (NAME + ".zip")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        license_index = {}
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                relative = path.relative_to(folder)
                # Keep Explorer extraction paths short, including bundled notices.
                # Preserve every license verbatim and record its original location.
                if relative.parts[0] == "THIRD_PARTY_LICENSES":
                    short_name = f"{len(license_index) + 1:04d}.txt"
                    license_index[short_name] = relative.as_posix()
                    archive.write(path, "WSI/licenses/" + short_name)
                else:
                    archive.write(path, "WSI/" + relative.as_posix())
        archive.writestr("WSI/licenses/INDEX.json", json.dumps(license_index, indent=2))
    (ROOT / "release" / (NAME + ".sha256")).write_text(
        hashlib.sha256(archive_path.read_bytes()).hexdigest() + "  " + archive_path.name + "\n", encoding="ascii")
    print(archive_path)
    print("EXE bytes:", exe.stat().st_size, "ZIP bytes:", archive_path.stat().st_size)


if __name__ == "__main__":
    main()
