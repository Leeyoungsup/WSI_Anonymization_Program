"""Pyramid metadata boundary, byte preservation, bounded thumbnail and masks."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import imagecodecs
import numpy as np
import openslide
import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi, ExportCancelled, _jpeg_header, _jpeg_entropy


class PyramidTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "input.tiff"
        pixels = np.random.default_rng(7).integers(0, 256, (1024, 2048, 3), dtype=np.uint8)
        with tifffile.TiffWriter(self.source) as writer:
            writer.write(pixels, tile=(128,128), compression="jpeg", photometric="rgb", description="PATIENT_SENTINEL")
            writer.write(np.zeros((24,64,3), dtype=np.uint8), photometric="rgb", description="PATIENT_SENTINEL_LABEL")
            writer.write(pixels[::2,::2], tile=(128,128), compression="jpeg", photometric="rgb",
                         subfiletype=1, description="PATIENT_SENTINEL_REDUCED")

    def tearDown(self):
        self.temp.cleanup()

    def test_default_pyramid_preserves_native_levels_and_fast_thumbnail(self):
        original_encode = imagecodecs.jpeg_encode
        calls = []
        def encode(array, **kwargs):
            calls.append(array.shape)
            return original_encode(array, **kwargs)
        with patch.object(imagecodecs, "jpeg_encode", encode):
            result = anonymize_wsi(self.source, self.root / "out")
        self.assertEqual(result["level_dimensions"], [[2048,1024],[1024,512],[256,128]])
        self.assertEqual(result["preserved_levels"], 2)
        self.assertEqual(result["generated_levels"], 1)
        self.assertFalse(result["base_image_reencoded"])
        self.assertEqual(calls, [(256,256,3)])
        self.assertNotIn(b"PATIENT_SENTINEL", Path(result["output_path"]).read_bytes())
        with tifffile.TiffFile(self.source) as original, tifffile.TiffFile(result["output_path"]) as output:
            self.assertEqual([p.subfiletype for p in output.pages], [0,1,1])
            self.assertTrue(all(p.is_tiled and not p.subifds for p in output.pages))
            for original_index, output_index in ((0,0),(2,1)):
                a, b = original.pages[original_index], output.pages[output_index]
                for oa, na, ob, nb in zip(a.dataoffsets,a.databytecounts,b.dataoffsets,b.databytecounts):
                    original.filehandle.seek(oa); da=original.filehandle.read(na)
                    output.filehandle.seek(ob); db=output.filehandle.read(nb)
                    _, ia, _, _ = _jpeg_header(da)
                    _, ib, _, _ = _jpeg_header(db)
                    self.assertEqual(_jpeg_entropy(da[ia:]), _jpeg_entropy(db[ib:]))
        with openslide.OpenSlide(result["output_path"]) as slide:
            original_read = slide.read_region
            levels = []
            def read(location, level, size):
                levels.append(level)
                self.assertGreater(level, 0)
                return original_read(location, level, size)
            with patch.object(slide, "read_region", read):
                with slide.get_thumbnail((256,256)) as thumbnail:
                    self.assertEqual(thumbnail.size, (256,128))
            self.assertTrue(levels)
            self.assertFalse(slide.associated_images)
        with Path(result["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(next(csv.DictReader(stream))["output_pages"], "3")

    def test_lossless_masks_propagate_to_generated_levels(self):
        result = anonymize_wsi(self.source, self.root / "out", compression="lossless",
                               redactions=[(0,0,1024,1024)])
        self.assertEqual(result["preserved_levels"], 0)
        with tifffile.TiffFile(result["output_path"]) as tif:
            self.assertTrue(np.all(tif.pages[1].asarray()[32:64,32:64] == 255))
            self.assertEqual(len(tif.pages), 2)

    def test_pyramid_cancel_cleans_all_partial_levels(self):
        stop = False
        def progress(event):
            nonlocal stop
            if event["stage"] == "pyramid":
                stop = True
        with self.assertRaises(ExportCancelled):
            anonymize_wsi(self.source, self.root / "out", progress=progress, cancelled=lambda: stop)
        self.assertFalse(list((self.root / "out").rglob("*.tiff")))


if __name__ == "__main__":
    unittest.main()
