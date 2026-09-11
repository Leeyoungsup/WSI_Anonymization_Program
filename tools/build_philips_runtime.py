"""Build a standalone Python 3.7 runtime from official embed/wheel archives.

SDK binaries come verbatim from the user-provided research SDK ZIP. No Conda
interpreter or site-packages is used at runtime. Run with the build Python.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "build/philips_downloads"
TARGET = ROOT / "build/philips_runtime"
PYTHON_URL = "https://www.python.org/ftp/python/3.7.9/python-3.7.9-embed-amd64.zip"
WHEELS = ("numpy==1.21.6", "Pillow==9.5.0")


def unpack(archive, name, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive.read(name))


def main():
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    TARGET.mkdir(parents=True, exist_ok=True)
    python_zip = DOWNLOADS / PYTHON_URL.rsplit("/", 1)[1]
    if not python_zip.exists():
        with urllib.request.urlopen(PYTHON_URL, timeout=60) as response:
            python_zip.write_bytes(response.read())
    subprocess.run([sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--no-deps",
        "--platform", "win_amd64", "--python-version", "37", "--implementation", "cp", "--abi", "cp37m",
        "--dest", str(DOWNLOADS), *WHEELS], check=True)
    inputs = {python_zip.name: hashlib.sha256(python_zip.read_bytes()).hexdigest()}
    with zipfile.ZipFile(python_zip) as archive:
        for name in archive.namelist():
            if "/" in name or "\\" in name:
                raise ValueError("Unexpected Python embed path")
            unpack(archive, name, TARGET / name)
    (TARGET / "python37._pth").write_text("python37.zip\n.\nlib\nbridge\nimport site\n", encoding="ascii")
    for pattern in ("numpy-1.21.6-*.whl", "Pillow-9.5.0-*.whl"):
        wheel = next(DOWNLOADS.glob(pattern))
        inputs[wheel.name] = hashlib.sha256(wheel.read_bytes()).hexdigest()
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                parts = Path(name).parts
                if ".." in parts or Path(name).is_absolute():
                    raise ValueError("Unexpected wheel path")
                notice = any(word in name.lower() for word in ("license", "copying", "notice"))
                if name.endswith("/") or (not notice and any(p in ("tests", "test", "include", "_examples") for p in parts)):
                    continue
                if notice or Path(name).suffix.lower() in (".py", ".pyd", ".dll") or ".dist-info/" in name:
                    unpack(archive, name, TARGET / "lib" / name)
    sdk_zip = ROOT / "philips_bridge.zip"
    inputs[sdk_zip.name] = hashlib.sha256(sdk_zip.read_bytes()).hexdigest()
    prefix = "Philips_SDK/philips-pathologysdk-2.0-L1-windows10-py37-research/"
    with zipfile.ZipFile(sdk_zip) as sdk, zipfile.ZipFile(TARGET / "SDK.zip", "w", zipfile.ZIP_DEFLATED) as original:
        for name in sdk.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            # Keep the complete supplied Windows SDK and its documentation.
            original.writestr(name[len(prefix):], sdk.read(name))
            relative = name[len(prefix):]
            if relative == "EULA Research.license.txt":
                unpack(sdk, name, TARGET / "EULA.txt")
            elif relative == "PathologySDK.Product.Label.txt":
                unpack(sdk, name, TARGET / "SDK_LABEL.txt")
            for module in ("pixelengine", "softwarerenderbackend", "softwarerendercontext"):
                module_prefix = "Modules/philips.pathologysdk." + module + ".2.0-L1/" + module + "/"
                if relative.startswith(module_prefix):
                    remainder = relative[len(module_prefix):]
                    if "/" not in remainder and Path(remainder).suffix in (".py", ".pyd", ".dll"):
                        unpack(sdk, name, TARGET / "lib" / module / remainder)
    # App-local Microsoft VC runtime. These are redistributable runtime files,
    # not OS system DLLs. Record their provenance and hashes in the manifest.
    vc_root = Path(os.environ.get("PHILIPS_VC_RUNTIME", str(Path(sys.prefix))))
    for name in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll"):
        source = vc_root / name
        if not source.is_file():
            raise FileNotFoundError("Set PHILIPS_VC_RUNTIME to the VC redistributable DLL folder: " + name)
        shutil.copy2(source, TARGET / name)
        inputs["vc/" + name] = hashlib.sha256(source.read_bytes()).hexdigest()
    vc_metadata = next((vc_root / "conda-meta").glob("vc14_runtime-*.json"), None)
    if vc_metadata is not None:
        vc_package = json.loads(vc_metadata.read_text(encoding="utf-8"))
        vc_licenses = Path(vc_package["link"]["source"]) / "info/licenses"
        for name in ("LICENSE.TXT", "LICENSE.RTF"):
            shutil.copy2(vc_licenses / name, TARGET / ("VC_" + name))
    else:
        license_file = Path(os.environ["PHILIPS_VC_LICENSE"])
        shutil.copy2(license_file, TARGET / "VC_LICENSE.TXT")
    bridge = TARGET / "bridge"
    bridge.mkdir(exist_ok=True)
    for source in (ROOT / "philips_bridge").glob("*.py"):
        shutil.copy2(source, bridge / source.name)
    (TARGET / "RUNTIME.json").write_text(json.dumps({
        "python": "3.7.9-embed-amd64", "numpy": "1.21.6", "Pillow": "9.5.0",
        "sdk": "2.0-L1 Windows research", "scope": "internal research distribution",
        "inputs_sha256": inputs,
        "files_sha256": {p.relative_to(TARGET).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(TARGET.rglob("*")) if p.is_file() and p.name != "RUNTIME.json"
                          and "__pycache__" not in p.parts and p.suffix != ".pyc"},
    }, indent=2), encoding="utf-8")
    print("Standalone Philips runtime:", TARGET)


if __name__ == "__main__":
    main()
