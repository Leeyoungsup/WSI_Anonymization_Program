"""Pyramid metadata boundary, byte preservation, bounded thumbnail and masks."""
import csv
import json
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
            writer.write(pixels, tile=(128,128), compression="jpeg", photometric="rgb", description="PATIENT_SENTINEL", metadata=None)
            writer.write(np.zeros((24,64,3), dtype=np.uint8), photometric="rgb", description="PATIENT_SENTINEL_LABEL")
            writer.write(pixels[::2,::2], tile=(128,128), compression="jpeg", photometric="rgb",
                         subfiletype=1, description="PATIENT_SENTINEL_REDUCED")

    def tearDown(self):
        self.temp.cleanup()

    def test_numeric_objective_retained_without_source_text_and_roundtrip(self):
        with tifffile.TiffFile(self.source, mode="r+") as tif:
            tif.pages[0].tags[270].overwrite(json.dumps({
                "schema": "wsi-technical-v1", "objective_power": 40,
                "patient": "PATIENT_SENTINEL"}))
        for compression in ("preserve", "lossless"):
            result = anonymize_wsi(self.source, self.root / compression, compression=compression)
            self.assertEqual(result["objective_power"], 40)
            path = Path(result["output_path"])
            self.assertNotIn(b"PATIENT_SENTINEL", path.read_bytes())
            with tifffile.TiffFile(path) as tif:
                self.assertEqual(json.loads(tif.pages[0].description), result["technical_metadata"])
                self.assertEqual(result["technical_metadata"]["width_px"], 2048)
                self.assertTrue(all(270 not in p.tags for p in tif.pages[1:]))
            again = anonymize_wsi(path, self.root / "again", export_image=False)
            self.assertEqual(again["objective_power"], 40)

    def test_invalid_objective_is_omitted(self):
        for value in ("patient-name", True, -40, float("nan")):
            with tifffile.TiffFile(self.source, mode="r+") as tif:
                tif.pages[0].tags[270].overwrite(json.dumps({
                    "schema": "wsi-technical-v1", "objective_power": value}))
            result = anonymize_wsi(self.source, self.root / "invalid", export_image=False)
            self.assertIsNone(result["objective_power"])

    def test_physical_size_and_mpp_opt_out(self):
        from wsi_anonymizer import _technical_metadata
        self.assertEqual(_technical_metadata((2000, 1000), (.25, .5), 40)["physical_width_mm"], .5)
        with patch("wsi_anonymizer._numeric_property", side_effect=lambda slide, key:
                   {"openslide.mpp-x": .25, "openslide.mpp-y": .5}.get(key)):
            for enabled in (True, False):
                result = anonymize_wsi(self.source, self.root / "physical", preserve_mpp=enabled)
                with tifffile.TiffFile(result["output_path"]) as tif:
                    data = json.loads(tif.pages[0].description)
                    self.assertEqual(data["physical_width_mm"], .512 if enabled else None)
                    self.assertEqual(data["physical_height_mm"], .512 if enabled else None)
                    self.assertEqual(data["mpp_x_um"], .25 if enabled else None)
                with open(result["csv_path"], encoding="utf-8-sig", newline="") as stream:
                    row = list(csv.DictReader(stream))[-1]
                    self.assertEqual(float(row["physical_width_mm"]), .512)

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
