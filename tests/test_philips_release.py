"""Frozen EXE reads Philips using only the bundled runtime and a clean PATH."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
exe = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist/WSI_Anonymization.exe"
environment = {k: v for k, v in os.environ.items() if not k.startswith(("CONDA", "PYTHON", "QT_", "_PYI", "_MEI"))}
environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
environment.pop("PHILIPS_PYTHON", None)

with tempfile.TemporaryDirectory(prefix="philips_release_") as directory:
    root = Path(directory)
    environment["USERPROFILE"] = str(root / "no-conda-home")
    def run(action, name="20260511_124345.i2syntax", **options):
        job = {"source": str(ROOT / "data" / name), "output": str(root / "output"),
               "action": action, "cancel_file": str(root / "cancel"), **options}
        request, events = root / "job.json", root / "events.jsonl"
        request.write_text(json.dumps(job), encoding="utf-8")
        events.unlink(missing_ok=True)
        result = subprocess.run([str(exe), "--worker", "--job-file", str(request), "--events-file", str(events)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=environment, cwd=root, timeout=60)
        messages = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        return result.returncode, messages[-1]
    code, event = run("inspect")
    assert code == 0 and event["data"]["errors"] == [], event
    assert event["preview"]
    code, event = run("copy", export_image=False, include_filename=False)
    assert code == 0 and event["data"]["report"]["technical_metadata"]["source_vendor"] == "philips", event
    assert event["data"]["report"]["objective_power"] is None
    code, event = run("inspect", "20260514_084959.i2syntax")
    assert code == 0 and event["data"]["errors"] == [], event
    for name in ("20260511_124345.i2syntax", "20260514_084959.i2syntax"):
        code, event = run("copy", name, compression="philips", preserve_icc=True, include_filename=False)
        assert code == 0, event
        report = event["data"]["report"]
        assert report["format"] == "philips-isyntax"
        assert report["all_compressed_blocks_verified"] and not report["reencoded"]
        assert report["native_validation"]["header_whitelist_verified"]
        assert report["source_output_pixel_regions_verified"] >= 24
        assert abs(report["size_bytes"]-(ROOT/"data"/name).stat().st_size) < 100000
        code, event = run("inspect", report["output_path"])
        assert code == 0 and not event["data"]["errors"] and event["preview"], event
    invalid = root / "invalid.i2syntax"
    invalid.write_bytes(b"invalid synthetic SDK input")
    code, event = run("copy", str(invalid), compression="lossless")
    assert code == 1 and event["kind"] == "error", event
    assert not list((root / "output").rglob("*.tiff"))
print("Philips frozen EXE: bundled runtime, clean PATH/home, inspection/preview, CSV-only and unreadable input passed")
