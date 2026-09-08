"""Exercise the packaged worker without Python/Conda directories on PATH."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
import tifffile

ROOT = Path(__file__).resolve().parents[1]
exe = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist" / "WSI_Anonymization.exe"
environment = {key: value for key, value in os.environ.items()
               if not key.startswith(("CONDA", "PYTHON", "QT_", "_PYI", "_MEI"))}
environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")

with tempfile.TemporaryDirectory(prefix="release_test_") as temporary:
    folder = Path(temporary)
    source = folder / "input" / "synthetic.tiff"
    source.parent.mkdir()
    pixels = np.random.default_rng(8).integers(0, 256, (1024, 2048, 3), dtype=np.uint8)
    with tifffile.TiffWriter(source) as writer:
        for index, array in enumerate((pixels, pixels[::2, ::2])):
            writer.write(array, compression="jpeg", tile=(128,128), photometric="rgb",
                         subfiletype=index, description="PATIENT_SENTINEL")
    original = hashlib.sha256(source.read_bytes()).digest()

    def run(action="copy", **options):
        job = {"source": str(source), "output": str(folder / "output"), "action": action,
               "cancel_file": str(folder / "cancel"), **options}
        job_path, events_path = folder / "job.json", folder / "events.jsonl"
        job_path.write_text(json.dumps(job) + "\n", encoding="utf-8")
        events_path.unlink(missing_ok=True)
        result = subprocess.run([str(exe), "--worker", "--job-file", str(job_path), "--events-file", str(events_path)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                cwd=folder, env=environment, timeout=120)
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.startswith("{")]
        assert result.returncode == 0, (result.returncode, events, result.stderr)
        assert events and events[-1]["kind"] in ("result", "cancelled"), events
        return events[-1]

    assert run("inspect")["data"]["errors"] == []
    preserved = run()["data"]
    assert preserved["report"]["compression"] == "jpeg-preserved"
    assert preserved["report"]["preserved_levels"] == 2
    assert preserved["report"]["generated_levels"] == 1
    assert preserved["report"]["thumbnail_verified"] is True
    assert b"PATIENT_SENTINEL" not in Path(preserved["file"]).read_bytes()
    np.testing.assert_array_equal(tifffile.imread(source), tifffile.imread(preserved["file"]))
    lossless = run(compression="lossless", export_csv=False)["data"]
    assert lossless["csv_path"] is None
    assert lossless["report"]["compression"] == "deflate-lossless"
    csv_only = run(export_image=False, include_filename=False)["data"]
    assert csv_only["file"] is None
    with Path(csv_only["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
        assert next(csv.DictReader(stream))["original_filename"] == ""
    (folder / "cancel").touch()
    assert run()["kind"] == "cancelled"
    assert hashlib.sha256(source.read_bytes()).digest() == original
    assert not list((folder / "output").rglob("*.partial.tiff"))
print("Packaged EXE: inspection, JPEG preservation, Deflate, CSV-only, cancellation and source integrity passed")
