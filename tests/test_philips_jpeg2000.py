"""Bounded real SDK center crops from both samples, lossless TIFF and ICC."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wsi_anonymizer as engine

ROOT = Path(__file__).resolve().parents[1]
openslide, dll = engine._openslide()
try:
    with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
        for sample in sorted((ROOT / "data").glob("*.i2syntax")):
            stat = sample.stat()
            with engine.PhilipsSlide(sample) as original:
                origin = (original.dimensions[0] // 2, original.dimensions[1] // 2)
                expected = np.asarray(original.read_region(origin, 0, (768, 640))).copy()
                icc = original.icc
            real_open = engine._open_slide
            def cropped(path, reader, cancelled=None):
                slide = real_open(path, reader, cancelled)
                read = slide.read_region
                slide.read_region = lambda location, level, size: read(
                    (location[0] + origin[0], location[1] + origin[1]), level, size)
                slide.dimensions = (768, 640)
                return slide
            with patch.object(engine, "_open_slide", cropped):
                result = engine.anonymize_wsi(sample, directory, compression="jpeg2000",
                    include_filename=False, preserve_icc=True)
            assert result["compression"] == "jpeg2000-lossless"
            assert not result["additional_lossy_compression"]
            with openslide.OpenSlide(result["output_path"]) as output:
                np.testing.assert_array_equal(np.asarray(output.read_region((0, 0), 0, (768, 640))), expected)
                assert output.read_region((0, 0), 0, (1, 1)).info.get("icc_profile") == icc
                assert output.level_count == 2 and not output.associated_images
            assert sample.stat().st_mtime_ns == stat.st_mtime_ns
finally:
    if dll:
        dll.close()
print("Both Philips center crops: exact SDK/OpenSlide pixels, pyramid, ICC and source integrity passed")
