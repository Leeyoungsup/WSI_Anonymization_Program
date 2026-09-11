"""JPEG 2000 preserves every RGB pixel through tifffile and OpenSlide readers."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi, ExportCancelled, _openslide


class Jpeg2000ExportTest(unittest.TestCase):
    def test_lossless_jpeg2000(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = np.random.default_rng(87).integers(0, 256, (777, 1025, 3), dtype=np.uint8)
            source = root / "source.tiff"
            tifffile.imwrite(source, image, tile=(128, 128), photometric="rgb", compression="deflate",
                             description="PATIENT_SENTINEL", metadata=None)
            result = anonymize_wsi(source, root / "out", compression="jpeg2000", include_filename=False)
            self.assertFalse(result["additional_lossy_compression"])
            self.assertFalse(result["source_compressed_payload_copied"])
            self.assertEqual(result["source_output_pixel_regions_verified"], 0)
            self.assertIsNone(result["jpeg_quality"])
            self.assertGreater(result["verified_tiles"], 0)
            self.assertEqual(result["level_dimensions"][0], [1025, 777])
            self.assertNotIn(b"PATIENT_SENTINEL", Path(result["output_path"]).read_bytes())
            with tifffile.TiffFile(result["output_path"]) as tif:
                self.assertTrue(all(p.compression == 33005 and p.is_tiled for p in tif.pages))
                for page in tif.pages:
                    for offset, size in zip(page.dataoffsets, page.databytecounts):
                        tif.filehandle.seek(offset)
                        raw = tif.filehandle.read(size)
                        self.assertTrue(raw.startswith(b"\xff\x4f"))
                self.assertTrue(np.array_equal(tif.pages[0].asarray(), image))
            openslide, dll = _openslide()
            try:
                with openslide.OpenSlide(result["output_path"]) as slide:
                    self.assertEqual(slide.dimensions, (1025, 777))
                    np.testing.assert_array_equal(np.asarray(slide.read_region((0, 0), 0, slide.dimensions))[:, :, :3], image)
                    self.assertFalse(slide.associated_images)
                    self.assertLessEqual(max(slide.get_thumbnail((256, 256)).size), 256)
            finally:
                if dll:
                    dll.close()
            with Path(result["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["compression"], "jpeg2000-lossless")

            cancel = [False]
            def progress(event):
                cancel[0] = True
            with self.assertRaises(ExportCancelled):
                anonymize_wsi(source, root / "cancel", compression="jpeg2000", progress=progress, cancelled=lambda: cancel[0])
            self.assertFalse(list((root / "cancel").rglob("*.tiff")))


if __name__ == "__main__":
    unittest.main()
