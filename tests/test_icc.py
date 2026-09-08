import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import openslide
import tifffile
from PIL import ImageCms
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi


class IccTests(unittest.TestCase):
    def test_profile_options_and_original_vendor_roundtrip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tiff"
            icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            pixels = np.random.default_rng(6).integers(0, 256, (512, 1024, 3), dtype=np.uint8)
            tifffile.imwrite(source, pixels, compression="jpeg", tile=(128, 128), photometric="rgb",
                iccprofile=icc, metadata=None, description=json.dumps({"schema": "wsi-technical-v1",
                    "source_vendor": "hamamatsu", "objective_power": 40, "patient": "PATIENT_SENTINEL"}))
            for compression in ("preserve", "lossless"):
                for include in (False, True):
                    result = anonymize_wsi(source, root / "out", compression=compression, preserve_icc=include)
                    self.assertEqual(result["icc_profile_copied"], include)
                    self.assertEqual(result["metadata_clean"], not include)
                    self.assertEqual(result["source_vendor"], "hamamatsu")
                    self.assertNotIn(b"PATIENT_SENTINEL", Path(result["output_path"]).read_bytes())
                    with openslide.OpenSlide(result["output_path"]) as slide:
                        self.assertEqual(slide.properties["openslide.objective-power"], "40")
                        with slide.get_thumbnail((128, 128)) as thumbnail:
                            self.assertEqual(thumbnail.info.get("icc_profile"), icc if include else None)
                    with tifffile.TiffFile(result["output_path"]) as tif:
                        self.assertEqual(tif.pages[0].tags[34675].value if include else None, icc if include else None)
                        if not include:
                            self.assertTrue(all(34675 not in page.tags for page in tif.pages))
                    again = anonymize_wsi(result["output_path"], root / "again", export_image=False)
                    self.assertEqual(again["technical_metadata"]["source_vendor"], "hamamatsu")
                    with open(result["csv_path"], encoding="utf-8-sig", newline="") as stream:
                        row = next(csv.DictReader(stream))
                    self.assertEqual(row["source_vendor"], "hamamatsu")
                    self.assertEqual(row["icc_review_required"], str(include))

    def test_absent_icc_and_vendor_text_not_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "input.tiff"
            tifffile.imwrite(path, np.zeros((32, 32, 3), dtype=np.uint8), compression="jpeg", tile=(16, 16),
                photometric="rgb", metadata=None, description=json.dumps({"schema": "wsi-technical-v1", "source_vendor": "PATIENT_SENTINEL"}))
            result = anonymize_wsi(path, root / "out", preserve_icc=True)
            self.assertFalse(result["icc_profile_copied"])
            self.assertTrue(result["metadata_clean"])
            self.assertEqual(result["source_vendor"], "generic-tiff")
            self.assertNotIn(b"PATIENT_SENTINEL", Path(result["output_path"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
