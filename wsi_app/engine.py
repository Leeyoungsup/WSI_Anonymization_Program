"""GUI adapter; the reusable conversion engine lives entirely in wsi_anonymizer.py."""
from pathlib import Path

from wsi_anonymizer import anonymize_wsi


def create_anonymized_tiff(source, output, *, run_id=None, pixels_reviewed=False, progress=None, cancelled=None,
                          export_image=True, export_csv=True, include_filename=True,
                          preserve_mpp=True, compression="preserve"):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source.parent or output.is_relative_to(source.parent):
        raise ValueError("출력 폴더는 원본 폴더 밖으로 선택하세요.")
    report = anonymize_wsi(source, output, run_id=run_id, pixels_reviewed=pixels_reviewed,
                           progress=progress, cancelled=cancelled, export_image=export_image,
                           export_csv=export_csv, include_filename=include_filename,
                           preserve_mpp=preserve_mpp, compression=compression)
    return {"directory": report["directory"], "file": report["output_path"],
            "csv_path": report["csv_path"], "report": report}
