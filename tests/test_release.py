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
import openslide
from PIL import ImageCms

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
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    with tifffile.TiffWriter(source) as writer:
        for index, array in enumerate((pixels, pixels[::2, ::2])):
            writer.write(array, compression="jpeg", tile=(128,128), photometric="rgb",
                         subfiletype=index, metadata=None, iccprofile=icc,
                         resolution=(40000, 20000), resolutionunit="CENTIMETER",
                         description=json.dumps({"schema": "wsi-technical-v1", "objective_power": 40,
                                                 "patient": "PATIENT_SENTINEL"}))
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
    audit = preserved["report"]["anonymization_audit"]
    assert next(e for e in audit["entries"] if e["item"] == "description")["status"] == "rewritten"
    assert "PATIENT_SENTINEL" not in json.dumps(audit)
    assert preserved["report"]["objective_power"] == 40
    with openslide.OpenSlide(preserved["file"]) as slide:
        assert slide.properties["openslide.objective-power"] == "40"
        assert slide.properties["openslide.vendor"] == "aperio"
    technical = preserved["report"]["technical_metadata"]
    assert technical["width_px"] == 2048 and technical["height_px"] == 1024
    assert technical["mpp_x_um"] == .25 and technical["mpp_y_um"] == .5
    assert technical["physical_width_mm"] == .512 and technical["physical_height_mm"] == .512
    with tifffile.TiffFile(preserved["file"]) as tif:
        assert json.loads(tif.pages[0].description.split("|WSI_Technical=", 1)[1]) == technical
    assert b"PATIENT_SENTINEL" not in Path(preserved["file"]).read_bytes()
    np.testing.assert_array_equal(tifffile.imread(source), tifffile.imread(preserved["file"]))
    lossless = run(compression="lossless", export_csv=False)["data"]
    named = run(rename_output=False)["data"]
    colored = run(preserve_icc=True)["data"]
    assert colored["report"]["icc_profile_copied"] and not colored["report"]["metadata_clean"]
    with openslide.OpenSlide(colored["file"]) as slide:
        with slide.read_region((0, 0), 0, (32, 32)) as region:
            assert region.info["icc_profile"] == icc
    assert Path(named["file"]).name == "synthetic.tiff"
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
