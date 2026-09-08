"""Regression tests for byte-preserving JPEG export and NDPI restart regrouping."""
import csv
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import imagecodecs
import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi, ExportCancelled, _jpeg_header, _jpeg_entropy, _preserve_jpeg


SENTINEL = b"PATIENT_SECRET_987654"


def marker(code, payload):
    return bytes((255, code)) + struct.pack(">H", len(payload) + 2) + payload


class PreservedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.tif"
        self.pixels = np.random.default_rng(52).integers(0, 256, (48, 80, 3), dtype=np.uint8)
        self.payloads = []
        for y in range(0, 48, 32):
            for x in range(0, 80, 32):
                tile = np.zeros((32, 32, 3), dtype=np.uint8)
                block = self.pixels[y:y + 32, x:x + 32]
                tile[:block.shape[0], :block.shape[1]] = block
                jpeg = imagecodecs.jpeg_encode(tile, level=90, subsampling=(2, 2))
                self.payloads.append(jpeg[:2] + marker(0xE1, SENTINEL) + marker(0xFE, SENTINEL) + jpeg[2:] + SENTINEL)
        with tifffile.TiffWriter(self.source) as writer:
            writer.write(iter(self.payloads), shape=self.pixels.shape, dtype=np.uint8,
                         tile=(32, 32), compression="jpeg", photometric="ycbcr", subsampling=(2, 2),
                         description=SENTINEL.decode(), metadata=None)
            writer.write(np.zeros((16, 16, 3), dtype=np.uint8), photometric="rgb", description=SENTINEL.decode())
        with self.source.open("ab") as stream:
            stream.write(SENTINEL)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_preserves_entropy_pixels_and_removes_metadata(self):
        before = hashlib.sha256(self.source.read_bytes()).digest()
        with patch.object(imagecodecs, "jpeg_encode", side_effect=AssertionError("Must not re-encode")):
            result = anonymize_wsi(self.source, self.root / "out")
        self.assertFalse(result["reencoded"])
        self.assertEqual(result["compression"], "jpeg-preserved")
        target = Path(result["output_path"])
        self.assertNotIn(SENTINEL, target.read_bytes())
        self.assertEqual(before, hashlib.sha256(self.source.read_bytes()).digest())
        with tifffile.TiffFile(self.source) as source, tifffile.TiffFile(target) as output:
            self.assertEqual(len(output.pages), 1)
            self.assertFalse(output.pages[0].subifds)
            np.testing.assert_array_equal(source.pages[0].asarray(), output.pages[0].asarray())
            for original, offset, count in zip(self.payloads, output.pages[0].dataoffsets, output.pages[0].databytecounts):
                output.filehandle.seek(offset)
                clean = output.filehandle.read(count)
                _, a, _, _ = _jpeg_header(original)
                _, b, _, _ = _jpeg_header(clean)
                self.assertEqual(_jpeg_entropy(original[a:]), _jpeg_entropy(clean[b:]))
        with Path(result["csv_path"]).open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(next(csv.DictReader(stream))["compression"], "jpeg-preserved")

    def test_ndpi_restart_rows_keep_all_pixels_and_coding_data(self):
        # Model tifffile's virtual NDPI tiles with genuine independent JPEG MCU
        # rows. Distinct spatial content catches accidental raster reordering.
        tw, th, cols, rows = 32, 8, 3, 4
        pixels = np.random.default_rng(15).integers(0, 256, (th * rows, tw * cols, 3), dtype=np.uint8)
        parts, offsets, counts, expected = [], [], [], np.zeros_like(pixels)
        header = None
        for row in range(rows):
            for col in range(cols):
                jpeg = imagecodecs.jpeg_encode(pixels[row*th:(row+1)*th, col*tw:(col+1)*tw], level=80, subsampling=(1, 1))
                clean, start, _, _ = _jpeg_header(jpeg)
                # Add the restart interval before SOS in the shared NDPI header.
                sos = clean.index(b"\xff\xda")
                header = clean[:sos] + marker(0xDD, struct.pack(">H", tw // 8)) + clean[sos:]
                header = header[:2] + marker(0xFE, SENTINEL) + header[2:]
                part = _jpeg_entropy(jpeg[start:]) + bytes((255, 0xD0 + (row*cols+col) % 8))
                offsets.append(sum(counts))
                counts.append(len(part))
                parts.append(part)
                expected[row*th:(row+1)*th, col*tw:(col+1)*tw] = imagecodecs.jpeg_decode(jpeg)
        raw = self.root / "restart.bin"
        raw.write_bytes(b"".join(parts))
        page = SimpleNamespace(imagewidth=tw*cols, imagelength=th*rows, compression=7,
                               photometric=6, planarconfig=1, jpegtables=None, is_tiled=True,
                               tilewidth=tw, tilelength=th, is_ndpi=True, jpegheader=header,
                               dataoffsets=offsets, databytecounts=counts)
        original_tiff = tifffile.TiffFile

        class FakeNDPI:
            def __enter__(inner):
                inner.pages = [page]
                inner.filehandle = raw.open("rb")
                return inner

            def __exit__(inner, *args):
                inner.filehandle.close()

        def open_tiff(path, *args, **kwargs):
            return FakeNDPI() if path == raw else original_tiff(path, *args, **kwargs)

        output = self.root / "ndpi.tiff"
        with patch("wsi_anonymizer.tifffile.TiffFile", side_effect=open_tiff), \
                patch.object(imagecodecs, "jpeg_encode", side_effect=AssertionError("Must not re-encode")):
            count = _preserve_jpeg(raw, output, [(tw*cols, th*rows)], None, lambda *a: None)
        self.assertEqual(count, 6)
        self.assertNotIn(SENTINEL, output.read_bytes())
        np.testing.assert_array_equal(tifffile.imread(output), expected)

    def test_reject_masks_and_unsupported_compression_without_fallback(self):
        with self.assertRaisesRegex(ValueError, "redactions require"):
            anonymize_wsi(self.source, self.root / "out", redactions=[(0, 0, 2, 2)])
        other = self.root / "deflate.tif"
        tifffile.imwrite(other, self.pixels, compression="deflate", tile=(32, 32), photometric="rgb")
        with self.assertRaisesRegex(ValueError, "no automatic recompression"):
            anonymize_wsi(other, self.root / "out")
        self.assertFalse(list((self.root / "out").rglob("*.tiff")))

    def test_cancel_cleanup(self):
        def progress(event):
            self.cancel = event["stage"] == "verify"
        self.cancel = False
        with self.assertRaises(ExportCancelled):
            anonymize_wsi(self.source, self.root / "out", progress=progress, cancelled=lambda: self.cancel)
        self.assertFalse(list((self.root / "out").rglob("*.tiff")))

    def test_corrupted_compressed_output_is_not_published(self):
        changed = False
        def progress(event):
            nonlocal changed
            if event["stage"] == "verify" and not changed:
                changed = True
                target = next((self.root / "out").rglob("*.partial.tiff"))
                with tifffile.TiffFile(target) as tif:
                    offset = tif.pages[0].dataoffsets[0]
                with target.open("r+b") as stream:
                    stream.seek(offset)
                    stream.write(b"XX")
        with self.assertRaises(Exception):
            anonymize_wsi(self.source, self.root / "out", progress=progress)
        self.assertTrue(changed)
        self.assertFalse(list((self.root / "out").rglob("*.tiff")))

    def test_portable_cli_defaults_to_preserve(self):
        module = self.root / "wsi_anonymizer.py"
        module.write_bytes((Path(__file__).resolve().parents[1] / module.name).read_bytes())
        run = subprocess.run([sys.executable, "-I", str(module), str(self.source), str(self.root / "out")],
                             cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('"reencoded": false', run.stdout)


if __name__ == "__main__":
    unittest.main()
