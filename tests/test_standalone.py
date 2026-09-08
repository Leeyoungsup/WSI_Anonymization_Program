import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi, ExportCancelled


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "patient_SOURCE_ID.tif"
        self.pixels = np.random.default_rng(12).integers(0, 256, (300, 530, 3), dtype=np.uint8)
        with tifffile.TiffWriter(self.source) as writer:
            for level, array in enumerate((self.pixels, self.pixels[::2, ::2])):
                writer.write(array, tile=(128, 128), photometric="rgb", compression="deflate", subfiletype=level,
                             description="PATIENT_SENTINEL_73918", software="PATIENT_SENTINEL_73918",
                             extratags=[(65000, "s", 0, "PATIENT_SENTINEL_73918", False)])
            writer.write(np.zeros((20, 20, 3), dtype=np.uint8), photometric="rgb",
                         description="PATIENT_SENTINEL_73918")
        with self.source.open("ab") as stream:
            stream.write(b"UNREFERENCED_PATIENT_SENTINEL_73918")
        self.original_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def test_clean_metadata_all_pixels_and_all_level_masks(self):
        target = self.root / "clean.tiff"
        result = anonymize_wsi(self.source, target, redactions=[(120, 110, 40, 50)],
                               tile_size=128, pixels_reviewed=True)
        self.assertTrue(result["all_output_tiles_verified"])
        self.assertEqual(result["status"], "metadata_clean_pixels_reviewed")
        self.assertNotIn(b"PATIENT_SENTINEL", target.read_bytes())
        with tifffile.TiffFile(target) as tif:
            self.assertEqual(len(tif.pages), 2)
            expected = self.pixels.copy()
            expected[110:160, 120:160] = 255
            np.testing.assert_array_equal(tif.pages[0].asarray(), expected)
            lower = tif.pages[1].asarray()
            self.assertTrue(np.all(lower[55:80, 60:80] == 255))
            for page in tif.pages:
                self.assertFalse(any(int(t.dtype) == 2 for t in page.tags.values()))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)

    def test_no_overwrite_or_invalid_masks(self):
        with self.assertRaises(FileExistsError):
            anonymize_wsi(self.source, self.source)
        target = self.root / "existing.tiff"
        target.write_bytes(b"do not touch")
        with self.assertRaises(FileExistsError):
            anonymize_wsi(self.source, target)
        self.assertEqual(target.read_bytes(), b"do not touch")
        with self.assertRaises(ValueError):
            anonymize_wsi(self.source, self.root / "bad.tiff", redactions=[(0, 0, 999, 999)])

    def test_cancel_and_cleanup(self):
        target = self.root / "cancel.tiff"
        with self.assertRaises(ExportCancelled):
            anonymize_wsi(self.source, target, cancelled=lambda: True)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob(".wsi_*")))

    def test_one_file_runs_outside_repository(self):
        module = self.root / "wsi_anonymizer.py"
        shutil.copyfile(Path(__file__).resolve().parents[1] / module.name, module)
        target = self.root / "portable.tiff"
        completed = subprocess.run([sys.executable, "-I", str(module), str(self.source), str(target)],
                                   cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(target.exists())
        self.assertIn("metadata_clean_pixel_review_required", completed.stdout)


if __name__ == "__main__":
    unittest.main()
