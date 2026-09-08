"""Full-size pyramid exports and CSV under output/<timestamp>/."""
import hashlib
import json
from pathlib import Path
import sys
import time
from datetime import datetime
import csv
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi

root = Path(__file__).resolve().parents[1]
reports = []
run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
record_path = root / "artifacts" / "pyramid_tiff_validation.json"
if "--resume" in sys.argv:
    reports = json.loads(record_path.read_text(encoding="utf-8"))
    assert all(Path(report["output_path"]).is_file() for report in reports)
    run_id = Path(reports[0]["directory"]).name
for source in sorted((root / "data").iterdir()):
    if source.suffix.lower() not in {".svs", ".ndpi"}:
        continue
    if source.suffix in {report["source_extension"] for report in reports}:
        continue
    with source.open("rb") as stream:
        before = hashlib.file_digest(stream, "sha256").digest()
    start = time.monotonic()
    last = [-1]

    def progress(event):
        percent = int(event["percent"])
        if percent != last[0]:
            print(source.suffix + " " + event["stage"] + " " + str(percent) + "%", flush=True)
            last[0] = percent

    result = anonymize_wsi(source, root / "output", run_id=run_id, progress=progress)
    with tifffile.TiffFile(result["output_path"]) as tif:
        assert len(tif.pages) >= 3 and all(p.is_tiled and not p.subifds for p in tif.pages)
        assert tif.pages[0].compression == 7
    assert result["base_image_reencoded"] is False
    assert result["thumbnail_verified"] is True
    with source.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").digest() == before
    result["source_extension"] = source.suffix
    result["original_sha256_unchanged"] = True
    result["elapsed_seconds"] = round(time.monotonic() - start, 1)
    reports.append(result)
    (root / "artifacts" / "pyramid_tiff_validation.json").write_text(
        json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
with Path(reports[-1]["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
    rows = list(csv.DictReader(stream))
assert len(rows) == len(reports)
assert all(row["mpp_x_um"] and row["mpp_y_um"] and int(row["output_pages"]) >= 3 for row in rows)
print("Shared timestamp folder and CSV rows verified", flush=True)
