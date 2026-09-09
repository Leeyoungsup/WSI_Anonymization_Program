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


class AuditTests(unittest.TestCase):
    def test_observed_removal_retention_and_no_value_disclosure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "patient-name.tiff"
            icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            with tifffile.TiffWriter(source) as writer:
                writer.write(np.zeros((128, 256, 3), dtype=np.uint8), tile=(64, 64),
                    compression="jpeg", photometric="rgb", metadata=None,
                    description="Aperio test|AppMag=40|Patient=PRIVATE_SENTINEL",
                    software="PRIVATE_SENTINEL", datetime="2026:09:09 12:00:00", iccprofile=icc,
                    extratags=[(65000, "s", 0, "PRIVATE_SENTINEL", False)])
                for name in ("thumbnail", "label", "macro"):
                    writer.write(np.zeros((16, 32, 3), dtype=np.uint8), photometric="rgb",
                        metadata=None, subfiletype={"thumbnail": 0, "label": 1, "macro": 9}[name],
                        description="Aperio test\n" + name + " PRIVATE_SENTINEL")
            with openslide.OpenSlide(str(source)) as slide:
                self.assertTrue({"label", "macro", "thumbnail"}.issubset(slide.associated_images))
            for keep in (False, True):
                result = anonymize_wsi(source, root / "out", preserve_icc=keep,
                                       rename_output=not keep, include_filename=keep)
                audit = result["anonymization_audit"]
                states = {entry["item"]: entry["status"] for entry in audit["entries"]}
                self.assertEqual(states["description"], "rewritten")
                entries = {entry["item"]: entry for entry in audit["entries"]}
                self.assertEqual(entries["description"]["before"], "present")
                self.assertEqual(entries["description"]["after"], "technical_metadata")
                self.assertEqual(entries["software"]["after"], "absent")
                self.assertEqual(entries["artist"]["before"], "absent")
                for name in ("software", "datetime", "label", "macro", "thumbnail"):
                    self.assertEqual(states[name], "removed")
                self.assertEqual(states["artist"], "not_present")
                self.assertEqual(states["icc"], "retained" if keep else "removed")
                self.assertEqual(states["filename"], "retained" if keep else "renamed")
                self.assertEqual(states["csv_filename"], "retained" if keep else "excluded")
                self.assertEqual(states["pixels"], "review_required")
                self.assertIn(65000, audit["removed_tag_codes"])
                self.assertNotIn("PRIVATE_SENTINEL", json.dumps(audit))
                self.assertNotIn("patient-name", json.dumps(audit))
                with open(result["csv_path"], encoding="utf-8-sig", newline="") as stream:
                    row = next(csv.DictReader(stream))
                self.assertEqual(json.loads(row["anonymization_audit"]), audit)
            only = anonymize_wsi(source, root / "csv", export_image=False)
            self.assertNotIn("anonymization_audit", only)
            with open(only["csv_path"], encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["anonymization_audit"], "")


if __name__ == "__main__":
    unittest.main()
