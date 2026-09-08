"""GUI adapter; the reusable conversion engine lives entirely in wsi_anonymizer.py."""
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from wsi_anonymizer import anonymize_wsi


def create_anonymized_tiff(source, output, *, pixels_reviewed=False, progress=None, cancelled=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source.parent or output.is_relative_to(source.parent):
        raise ValueError("출력 폴더는 원본 폴더 밖으로 선택하세요.")
    output.mkdir(parents=True, exist_ok=True)
    token = "anonymous_" + uuid.uuid4().hex
    pending = Path(tempfile.mkdtemp(prefix=".pending_", dir=output))
    final = output / token
    try:
        name = token + ".tiff"
        report = anonymize_wsi(source, pending / name, pixels_reviewed=pixels_reviewed,
                               progress=progress, cancelled=cancelled)
        report["output_path"] = str(final / name)
        (pending / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        pending.rename(final)
        return {"directory": str(final), "file": str(final / name), "report": report}
    finally:
        if pending.exists():
            shutil.rmtree(pending)
