"""Full-size sample exports. Keeps the resulting TIFFs under output/clean_tiff/."""
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi

root = Path(__file__).resolve().parents[1]
reports = []
for source in sorted((root / "data").iterdir()):
    if source.suffix.lower() not in {".svs", ".ndpi"}:
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

    target = root / "output" / "clean_tiff" / ("anonymous_" + uuid.uuid4().hex + ".tiff")
    result = anonymize_wsi(source, target, progress=progress)
    with source.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").digest() == before
    result["source_extension"] = source.suffix
    result["original_sha256_unchanged"] = True
    result["elapsed_seconds"] = round(time.monotonic() - start, 1)
    reports.append(result)
    (root / "artifacts" / "full_tiff_validation.json").write_text(
        json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
