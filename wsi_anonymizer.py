"""Standalone WSI -> clean pyramidal BigTIFF export (Python 3.10+).

Copy this file to another project. Dependencies:
    pip install openslide-python openslide-bin numpy tifffile imagecodecs Pillow

    from wsi_anonymizer import anonymize_wsi
    result = anonymize_wsi('slide.ndpi', 'export/anonymous.tiff')

Only decoded RGB pixels and optional numeric calibration cross into the output.
All OpenSlide-readable formats use the SAME export path. This exports OpenSlide's
2D RGB representation, not all channels/focal planes of multidimensional inputs.
No OCR can establish that arbitrary image pixels contain no identifiers. The
caller must review pixels, and can supply level-0 rectangles to erase. Setting
pixels_reviewed=True records a caller assertion, not an automated certification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from collections.abc import Callable, Sequence

import numpy as np
import tifffile

__all__ = ["anonymize_wsi", "ExportCancelled"]


class ExportCancelled(Exception):
    """Export cancelled before final publication; temporary output is removed."""


def _openslide():
    handle = None
    if os.name == "nt":
        spec = importlib.util.find_spec("openslide_bin")
        if spec and spec.origin:
            handle = os.add_dll_directory(str(Path(spec.origin).parent))
    try:
        import openslide
        version = tuple(int(v) for v in openslide.__library_version__.split(".")[:3])
        if version < (4, 0, 1):
            raise RuntimeError("OpenSlide 4.0.1+ is required for correct TIFF edge-tile decoding")
    except Exception:
        if handle:
            handle.close()
        raise
    return openslide, handle


def _rectangles(rectangles, width, height):
    result = []
    for rectangle in rectangles:
        if len(rectangle) != 4 or any(isinstance(v, bool) or not isinstance(v, int) for v in rectangle):
            raise ValueError("Each redaction must be four integers: x, y, width, height")
        x, y, w, h = rectangle
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise ValueError("Redaction is outside the level-0 image")
        result.append((x, y, w, h))
    return result


def _rgb_tile(slide, level, x, y, tile_size, boxes):
    downsample = slide.level_downsamples[level]
    location = (int(x * downsample), int(y * downsample))
    with slide.read_region(location, level, (tile_size, tile_size)) as region:
        rgba = np.asarray(region)
        # Flatten transparency on white; never retain hidden transparent RGB.
        if np.all(rgba[:, :, 3] == 255):
            rgb = rgba[:, :, :3].copy()
        else:
            alpha = rgba[:, :, 3:4].astype(np.uint16)
            rgb = ((rgba[:, :, :3].astype(np.uint16) * alpha +
                    255 * (255 - alpha) + 127) // 255).astype(np.uint8)
    width, height = slide.level_dimensions[level]
    if x + tile_size > width:
        rgb[:, max(0, width - x):] = 255
    if y + tile_size > height:
        rgb[max(0, height - y):, :] = 255
    for rx, ry, rw, rh in boxes:
        # Dilate lower-level masks by one pixel to cover rounding at boundaries.
        margin = 1 if level else 0
        left = max(0, math.floor((rx - location[0]) / downsample) - margin)
        top = max(0, math.floor((ry - location[1]) / downsample) - margin)
        right = min(tile_size, math.ceil((rx + rw - location[0]) / downsample) + margin)
        bottom = min(tile_size, math.ceil((ry + rh - location[1]) / downsample) + margin)
        if right > left and bottom > top:
            rgb[top:bottom, left:right] = 255
    return rgb


def anonymize_wsi(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    redactions: Sequence[Sequence[int]] = (),
    pixels_reviewed: bool = False,
    preserve_mpp: bool = True,
    tile_size: int = 512,
    workers: int = 4,
    progress: Callable[[dict], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Export any locally OpenSlide-readable WSI as a new lossless tiled TIFF.

    output_path: .tif/.tiff file, never overwritten; omitted -> random name beside
        input. Choose a nonidentifying name if providing one yourself.
    redactions: (x, y, width, height) in level-0 pixels, painted white at ALL levels.
        Lower-resolution representations can smear text beyond a rectangle;
        include a generous margin and review all resolutions.
    pixels_reviewed: caller confirms no identifiers remain outside supplied masks.
    preserve_mpp: copy only finite positive numeric microns-per-pixel calibration.
    progress: receives {stage, completed, total, percent}; no source identifiers.
    cancelled: cooperative callback evaluated between tiles; True aborts export.

    Always re-encodes decoded RGB using lossless Deflate and verifies EVERY output
    tile against the pixels supplied to the writer. It does not copy ICC profiles,
    source descriptions, associated images, JPEG payloads or unreferenced bytes.
    Pixel values are preserved after alpha flattening/redaction, but removing ICC
    can change color-managed viewer appearance. No OCR or legal certification is
    performed. Completion status explicitly distinguishes caller pixel review.

    Uses bounded tile buffers; final publication happens only after validation.
    The input must remain unchanged throughout export (including sidecar files).
    Returns a JSON-serializable report. Does not write an ID mapping or sidecar.
    """
    source = Path(input_path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("Input must be a WSI file")
    target = (Path(output_path).expanduser().resolve() if output_path is not None else
              source.parent / ("anonymous_" + uuid.uuid4().hex + ".tiff"))
    if target == source or target.exists():
        raise FileExistsError("Output already exists or refers to the input")
    if target.suffix.lower() not in {".tif", ".tiff"}:
        raise ValueError("Output must end with .tif or .tiff")
    if not isinstance(tile_size, int) or tile_size < 128 or tile_size > 2048 or tile_size % 16:
        raise ValueError("tile_size must be a multiple of 16 between 128 and 2048")
    if not isinstance(workers, int) or not 1 <= workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    if not isinstance(pixels_reviewed, bool):
        raise TypeError("pixels_reviewed must be a boolean")
    openslide, dll = _openslide()
    temporary = None

    def emit(stage, completed, total):
        if cancelled is not None and cancelled():
            raise ExportCancelled("Export cancelled")
        if progress is not None:
            base, scale = (0, 70) if stage == "write" else (70, 30)
            progress({"stage": stage, "completed": completed, "total": total,
                      "percent": round(base + scale * completed / max(1, total), 1)})

    try:
        stat_before = source.stat()
        with openslide.OpenSlide(str(source)) as slide:
            dimensions = list(slide.level_dimensions)
            downsamples = list(slide.level_downsamples)
            if any(w <= 0 or h <= 0 for w, h in dimensions):
                raise ValueError("Invalid image dimensions")
            if any(not math.isfinite(d) or d < 1 for d in downsamples):
                raise ValueError("Invalid image pyramid")
            boxes = _rectangles(redactions, *dimensions[0])
            mpp = None
            if preserve_mpp:
                try:
                    mx = float(slide.properties["openslide.mpp-x"])
                    my = float(slide.properties["openslide.mpp-y"])
                    if all(math.isfinite(v) and 0.000001 <= v <= 100000 for v in (mx, my)):
                        mpp = (mx, my)
                except (KeyError, ValueError, TypeError):
                    pass
            tiles_per_level = [math.ceil(w / tile_size) * math.ceil(h / tile_size)
                               for w, h in dimensions]
            total = sum(tiles_per_level)
            target.parent.mkdir(parents=True, exist_ok=True)
            # Deflate worst-case can approach raw size, including edge padding.
            required = int(total * tile_size * tile_size * 3 * 1.02) + 64 * 1024**2
            if shutil.disk_usage(target.parent).free < required:
                raise OSError("Not enough space for a worst-case lossless TIFF export")
            fd, name = tempfile.mkstemp(prefix=".wsi_", suffix=".partial.tiff", dir=target.parent)
            os.close(fd)
            temporary = Path(name)
            hashes = []
            written = 0
            emit("write", 0, total)

            with tifffile.TiffWriter(temporary, bigtiff=True) as writer:
                for level, (width, height) in enumerate(dimensions):
                    digest = hashlib.sha256()

                    def tiles():
                        nonlocal written
                        for y in range(0, height, tile_size):
                            for x in range(0, width, tile_size):
                                if cancelled is not None and cancelled():
                                    raise ExportCancelled("Export cancelled")
                                rgb = _rgb_tile(slide, level, x, y, tile_size, boxes)
                                digest.update(rgb.tobytes())
                                yield rgb
                                written += 1
                                if written % 128 == 0 or written == total:
                                    emit("write", written, total)

                    resolution = None if mpp is None else (
                        10000 / (mpp[0] * downsamples[level]),
                        10000 / (mpp[1] * downsamples[level]))
                    writer.write(
                        tiles(), shape=(height, width, 3), dtype=np.uint8,
                        tile=(tile_size, tile_size), photometric="rgb",
                        compression="deflate", compressionargs={"level": 1},
                        metadata=None, description=None, software=False, datetime=False,
                        resolution=resolution, resolutionunit="CENTIMETER" if mpp else "NONE",
                        subfiletype=0 if level == 0 else 1, maxworkers=workers,
                        buffersize=32 * 1024**2,
                    )
                    hashes.append(digest.hexdigest())

            # Whitelist exactly the structural tags our writer is allowed to emit.
            allowed_tags = {254, 256, 257, 258, 259, 262, 277, 282, 283, 284,
                            296, 322, 323, 324, 325}
            verified = 0
            emit("verify", 0, total)
            with tifffile.TiffFile(temporary) as tif:
                if len(tif.pages) != len(dimensions) or not tif.is_bigtiff:
                    raise ValueError("Unexpected output TIFF structure")
                for level, page in enumerate(tif.pages):
                    if set(page.tags.keys()) - allowed_tags:
                        raise ValueError("Unexpected metadata in output TIFF")
                    if any(int(tag.dtype) == 2 for tag in page.tags.values()):
                        raise ValueError("Text metadata detected in output TIFF")
                    if (page.imagewidth, page.imagelength) != dimensions[level] or not page.is_tiled:
                        raise ValueError("Output image dimensions do not match")
                    digest = hashlib.sha256()
                    count = 0
                    for data, _, _ in page.segments(maxworkers=workers, buffersize=32 * 1024**2):
                        if data is None:
                            raise ValueError("Missing output tile")
                        digest.update(data.tobytes())
                        count += 1
                        verified += 1
                        if verified % 128 == 0 or verified == total:
                            emit("verify", verified, total)
                    if count != tiles_per_level[level] or digest.hexdigest() != hashes[level]:
                        raise ValueError("Decoded output pixels do not match exported pixels")
            with openslide.OpenSlide(str(temporary)) as check:
                if list(check.level_dimensions) != dimensions or check.associated_images:
                    raise ValueError("Output pyramid readback failed")
                if check.properties.get("openslide.vendor") != "generic-tiff":
                    raise ValueError("Output is not a generic tiled TIFF")
                with check.read_region((0, 0), 0, (64, 64)) as region:
                    region.load()
            stat_after = source.stat()
            if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
                raise ValueError("Input changed during export")
            if cancelled is not None and cancelled():
                raise ExportCancelled("Export cancelled")
            # Atomic no-clobber publication on both Windows and POSIX.
            if os.name == "nt":
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
                temporary.unlink()
            temporary = None
            return {
                "output_path": str(target), "format": "pyramidal-bigtiff",
                "status": "metadata_clean_pixels_reviewed" if pixels_reviewed else "metadata_clean_pixel_review_required",
                "metadata_clean": True, "pixel_review_asserted_by_caller": pixels_reviewed,
                "redaction_count": len(boxes), "level_dimensions": [list(d) for d in dimensions],
                "mpp": list(mpp) if mpp else None, "compression": "deflate-lossless",
                "all_output_tiles_verified": True, "verified_tiles": verified,
                "source_metadata_copied": False, "associated_images_copied": False,
                "source_compressed_payload_copied": False, "icc_profile_copied": False,
                "representation": "OpenSlide 2D RGB; not all focal planes/channels",
                "size_bytes": target.stat().st_size,
            }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if dll is not None:
            dll.close()


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--pixels-reviewed", action="store_true")
    parser.add_argument("--redact", type=int, nargs=4, action="append", default=[], metavar=("X", "Y", "W", "H"))
    args = parser.parse_args()
    last = [-1]

    def show_progress(event):
        percent = int(event["percent"])
        if percent != last[0]:
            print(f"{event['stage']}: {percent}%", flush=True)
            last[0] = percent

    result = anonymize_wsi(args.input, args.output, redactions=args.redact,
                           pixels_reviewed=args.pixels_reviewed, progress=show_progress)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    _main()
