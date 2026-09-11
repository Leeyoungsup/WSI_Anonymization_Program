"""SDK integration: real sample regions, bounded export, cleanup and failures."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import numpy as np
import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wsi_anonymizer as engine
from tools.inspect_samples import inspect, load_openslide

ROOT = Path(__file__).resolve().parents[1]
sample = ROOT / "data/20260511_124345.i2syntax"
bad_sample = ROOT / "data/20260514_084959.i2syntax"


def main():
    openslide, dll = load_openslide()
    try:
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
            root = Path(directory)
            bad_sample = root / "invalid.i2syntax"
            bad_sample.write_bytes(b"invalid synthetic SDK input")
            stat = sample.stat()
            inventory = inspect(sample, "philips_001", openslide)
            assert inventory["errors"] == [], inventory["errors"]
            assert inventory["openslide"]["dimensions"] == (51996, 22145)
            assert inventory["openslide"]["objective_power"] is None
            assert len(inventory["openslide"]["decoded_regions"]) == 24
            with engine.PhilipsSlide(sample) as slide:
                expected = np.asarray(slide.read_region((0, 0), 0, (512, 512)))[:, :, :3].copy()
                icc = slide.icc
                process = slide._process
            assert process.poll() is not None

            # Exercise final export using a bounded real SDK region. Full-slide
            # conversion is verified separately in artifacts/philips_conversion_validation.json.
            real_open = engine._open_slide
            def cropped(path, reader, cancelled=None):
                slide = real_open(path, reader, cancelled)
                slide.dimensions = (768, 640)
                return slide
            with patch.object(engine, "_open_slide", cropped):
                report = engine.anonymize_wsi(sample, root, compression="lossless", include_filename=False,
                                              preserve_icc=True)
            assert report["compression"] == "deflate-lossless"
            assert report["source_vendor"] == "philips" and report["objective_power"] is None
            assert report["philips_display_origin"] == [2, 2]
            assert report["metadata_clean"] is False and report["icc_review_required"] is True
            assert report["technical_metadata"]["source_origin_x_px"] == 2
            assert any(e["item"] == "philips_metadata" for e in report["anonymization_audit"]["entries"])
            with openslide.OpenSlide(report["output_path"]) as output:
                np.testing.assert_array_equal(np.asarray(output.read_region((0, 0), 0, (512, 512)))[:, :, :3], expected)
                assert output.read_region((0, 0), 0, (1, 1)).info["icc_profile"] == icc
                assert not output.associated_images
            rows = list(csv.DictReader(Path(report["csv_path"]).open(encoding="utf-8-sig", newline="")))
            assert rows[0]["original_filename"] == "" and rows[0]["source_origin_x_px"] == "2"
            assert "barcode" not in json.dumps(report).lower()

            for path in (sample, bad_sample):
                try:
                    engine.anonymize_wsi(path, root / "reject", compression="preserve")
                    raise AssertionError("preserve accepted")
                except ValueError as exc:
                    assert "lossless" in str(exc)
            assert not (root / "reject").exists()
            try:
                engine.anonymize_wsi(bad_sample, root / "bad", compression="lossless")
                raise AssertionError("unreadable sample accepted")
            except ValueError as exc:
                assert "SDK" in str(exc) and bad_sample.name not in str(exc)
            assert not list((root / "bad").rglob("*.tiff"))
            cancelled = [False]
            def progress(event):
                cancelled[0] = True
            try:
                engine.anonymize_wsi(sample, root / "cancel", compression="lossless",
                    progress=progress, cancelled=lambda: cancelled[0])
                raise AssertionError("cancellation ignored")
            except engine.ExportCancelled:
                pass
            assert not list((root / "cancel").rglob("*.tiff"))
            assert not list((root / "cancel").rglob("*.csv"))

            csv_only = engine.anonymize_wsi(sample, root / "csv", export_image=False, include_filename=False)
            assert csv_only["format"] == "csv-only" and csv_only["objective_power"] is None
            assert sample.stat().st_size == stat.st_size and sample.stat().st_mtime_ns == stat.st_mtime_ns
            # Unicode basename as well as the existing Unicode parent directory.
            alias = root / ("\ud55c\uae00\uc774\ub984.i2syntax")
            os.link(sample, alias)
            with engine.PhilipsSlide(alias) as slide:
                assert slide.dimensions == (51996, 22145)
        print("Philips SDK: inventory, real region export, ICC, CSV, Unicode paths, reject/cancel and cleanup passed")
    finally:
        if dll is not None:
            dll.close()


if __name__ == "__main__":
    main()
