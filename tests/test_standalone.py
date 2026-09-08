import hashlib
import json
import csv
import uuid
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi as export_wsi, ExportCancelled
from functools import partial
anonymize_wsi = partial(export_wsi, compression="lossless", pyramid=False)


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

    def test_keep_filename_and_collision_preserve_existing_output(self):
        kwargs = dict(run_id="20260909_120000_000000", rename_output=False, include_filename=False)
        first = anonymize_wsi(self.source, self.root / "out", **kwargs)
        path = Path(first["output_path"])
        self.assertEqual(path.name, self.source.stem + ".tiff")
        digest = hashlib.sha256(path.read_bytes()).digest()
        second = anonymize_wsi(self.source, self.root / "out", **kwargs)
        self.assertEqual(Path(second["output_path"]).name, self.source.stem + "_2.tiff")
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)
        self.assertNotIn(self.source.stem.encode(), path.read_bytes())
        with open(second["csv_path"], encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r["original_filename"] for r in rows], ["", ""])
        self.assertEqual([r["output_filename"] for r in rows], [path.name, Path(second["output_path"]).name])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)

    def test_single_image_metadata_pixels_and_csv(self):
        result = anonymize_wsi(self.source, self.root / "output", redactions=[(120, 110, 40, 50)],
                               tile_size=128, pixels_reviewed=True)
        target = Path(result["output_path"])
        self.assertTrue(result["all_output_tiles_verified"])
        self.assertEqual(result["status"], "metadata_clean_pixels_reviewed")
        self.assertNotIn(b"PATIENT_SENTINEL", target.read_bytes())
        with tifffile.TiffFile(target) as tif:
            self.assertEqual(len(tif.pages), 1)
            self.assertFalse(tif.pages[0].subifds)
            expected = self.pixels.copy()
            expected[110:160, 120:160] = 255
            np.testing.assert_array_equal(tif.pages[0].asarray(), expected)
            for page in tif.pages:
                self.assertEqual([t.code for t in page.tags.values() if int(t.dtype) == 2], [270])
                self.assertEqual(json.loads(page.description.split("|WSI_Technical=", 1)[1]), result["technical_metadata"])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)
        with Path(result["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]["original_filename"], self.source.name)
        self.assertEqual(rows[0]["output_filename"], target.name)
        self.assertEqual(rows[0]["width_px"], "530")
        self.assertEqual(rows[0]["output_pages"], "1")
        self.assertNotIn("PATIENT_SENTINEL", Path(result["csv_path"]).read_text(encoding="utf-8-sig"))
        self.assertTrue(Path(result["csv_path"]).read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_no_overwrite_or_invalid_masks(self):
        with self.assertRaises(NotADirectoryError):
            anonymize_wsi(self.source, self.source)
        target = self.root / "existing.tiff"
        target.write_bytes(b"do not touch")
        with self.assertRaises(NotADirectoryError):
            anonymize_wsi(self.source, target)
        self.assertEqual(target.read_bytes(), b"do not touch")
        with self.assertRaises(ValueError):
            anonymize_wsi(self.source, self.root / "bad", redactions=[(0, 0, 999, 999)])

    def test_cancel_and_cleanup(self):
        target = self.root / "cancel"
        with self.assertRaises(ExportCancelled):
            anonymize_wsi(self.source, target, cancelled=lambda: True)
        self.assertFalse(list(target.rglob("*.tiff")))
        self.assertFalse(list(self.root.rglob(".wsi_*")))

    def test_one_file_runs_outside_repository(self):
        module = self.root / "wsi_anonymizer.py"
        shutil.copyfile(Path(__file__).resolve().parents[1] / module.name, module)
        target = self.root / "portable"
        completed = subprocess.run([sys.executable, "-I", str(module), str(self.source), str(target), "--compression", "lossless", "--single-image"],
                                   cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(list(target.rglob("*.tiff"))), 1)
        self.assertEqual(len(list(target.rglob("metadata.csv"))), 1)
        self.assertIn("metadata_clean_pixel_review_required", completed.stdout)

    def test_corrupt_output_is_not_published(self):
        target = self.root / "invalid"
        original_segments = tifffile.TiffPage.segments

        def corrupt(page, **kwargs):
            first = True
            for data, position, shape in original_segments(page, **kwargs):
                if first:
                    data = data.copy()
                    data.flat[0] ^= 1
                    first = False
                yield data, position, shape

        with patch.object(tifffile.TiffPage, "segments", corrupt):
            with self.assertRaisesRegex(ValueError, "pixels do not match"):
                anonymize_wsi(self.source, target)
        self.assertFalse(list(target.rglob("*.tiff")))
        self.assertFalse(list(self.root.rglob(".wsi_*")))

    def test_output_created_during_export_is_not_overwritten(self):
        output = self.root / "race"
        target = output / "20260908_120000_000001" / ("anonymous_" + uuid.UUID(int=0).hex + ".tiff")

        def race(event):
            if event["percent"] == 100:
                target.write_bytes(b"another process created this")

        with patch("wsi_anonymizer.uuid.uuid4", return_value=uuid.UUID(int=0)):
            with self.assertRaises(FileExistsError):
                anonymize_wsi(self.source, output, run_id="20260908_120000_000001", progress=race)
        self.assertEqual(target.read_bytes(), b"another process created this")
        self.assertFalse(list(self.root.rglob(".wsi_*")))

    def test_shared_run_csv_and_filename_quoting(self):
        other = self.root / "한글, 슬라이드.tif"
        shutil.copyfile(self.source, other)
        first = anonymize_wsi(self.source, self.root / "output", run_id="20260908_120000_000001")
        second = anonymize_wsi(other, self.root / "output", run_id="20260908_120000_000001")
        self.assertEqual(first["directory"], second["directory"])
        with Path(first["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r["original_filename"] for r in rows], [self.source.name, other.name])
        third = anonymize_wsi(other, self.root / "output")
        self.assertNotEqual(third["directory"], first["directory"])

    def test_csv_failure_does_not_publish_unrecorded_tiff(self):
        output = self.root / "output"
        with patch("wsi_anonymizer._record_csv", side_effect=OSError("CSV unavailable")):
            with self.assertRaises(OSError):
                anonymize_wsi(self.source, output)
        self.assertFalse(list(output.rglob("*.tiff")))

    def test_large_single_image_preview_does_not_load_full_image(self):
        from tools.inspect_samples import safe_thumbnail

        class LargeSlide:
            dimensions = (110562, 61468)
            level_dimensions = (dimensions,)

            def get_best_level_for_downsample(self, scale):
                return 0

            def get_thumbnail(self, size):
                raise AssertionError("Must not allocate a huge level-0 image")

        self.assertIsNone(safe_thumbnail(LargeSlide(), (700, 480)))

    def test_open_csv_gets_complete_snapshot_without_lost_rows(self):
        output = self.root / "output"
        run = "20260908_120000_000001"
        first = anonymize_wsi(self.source, output, run_id=run)
        with patch("wsi_anonymizer.os.replace", side_effect=PermissionError("Excel lock")):
            second = anonymize_wsi(self.source, output, run_id=run)
        self.assertNotEqual(first["csv_path"], second["csv_path"])
        self.assertTrue(Path(second["output_path"]).is_file())
        with Path(second["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 2)
        third = anonymize_wsi(self.source, output, run_id=run)
        with Path(third["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r["output_filename"] for r in rows}), 3)


if __name__ == "__main__":
    unittest.main()
