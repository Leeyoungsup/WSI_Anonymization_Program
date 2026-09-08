"""Standalone WSI -> single-image TIFF and technical CSV (Python 3.10+).

Copy this file to another project. Dependencies:
    pip install openslide-python "openslide-bin>=4.0.1.2" numpy tifffile imagecodecs Pillow

    from wsi_anonymizer import anonymize_wsi
    result = anonymize_wsi('slide.ndpi', 'output')

The default preserves baseline JPEG coding data from compatible SVS/TIFF tiles
and NDPI restart segments. APP/COM headers, private TIFF tags, associated images,
and unreferenced file bytes are excluded. Unsupported layouts fail explicitly;
they are never silently re-encoded. compression='lossless' explicitly selects
the previous decoded RGB/Deflate path for other OpenSlide-readable inputs/masks.
Only level 0 is exported, not all channels/focal planes of multidimensional inputs.
No OCR can establish that arbitrary image pixels contain no identifiers. The
caller must review pixels, and can supply level-0 rectangles to erase. Setting
pixels_reviewed=True records a caller assertion, not an automated certification.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile
import uuid
from collections.abc import Callable, Sequence

import numpy as np
import tifffile

__all__ = ["anonymize_wsi", "ExportCancelled"]

CSV_FIELDS = (
    "original_filename", "output_filename", "source_format", "mpp_x_um", "mpp_y_um",
    "width_px", "height_px", "objective_power", "source_level_count", "output_pages",
    "source_size_bytes", "output_size_bytes", "compression", "exported_at",
    "status", "verified_tiles", "pixel_review_asserted_by_caller",
)


def _numeric_property(slide, key):
    try:
        value = float(slide.properties[key])
        return value if math.isfinite(value) and 0.000001 <= value <= 100000 else None
    except (KeyError, ValueError, TypeError):
        return None


def _run_folder(base, run_id):
    base.mkdir(parents=True, exist_ok=True)
    if run_id is not None:
        if not isinstance(run_id, str) or len(run_id) != 22:
            raise ValueError("run_id must be YYYYMMDD_HHMMSS_ffffff")
        parsed = datetime.strptime(run_id, "%Y%m%d_%H%M%S_%f")
        if parsed.strftime("%Y%m%d_%H%M%S_%f") != run_id:
            raise ValueError("Invalid run_id")
        folder = base / run_id
        folder.mkdir(exist_ok=True)
        return folder
    while True:
        folder = base / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            continue


def _record_csv(folder, row):
    """Atomic manifest update. Concurrent writers fail instead of losing rows."""
    manifest = folder / "metadata.csv"
    lock = folder / ".metadata.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    temporary = None
    try:
        rows = []
        # Excel can keep the canonical CSV locked while more slides finish.
        # Continue from the newest complete snapshot, including CSV-only rows.
        manifests = ([manifest] if manifest.exists() else []) + list(folder.glob("metadata_*.csv"))
        for previous in sorted(manifests, key=lambda p: p.stat().st_mtime_ns):
            with previous.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != list(CSV_FIELDS):
                    raise ValueError("Existing metadata.csv has an unexpected schema")
                # Each file is a complete snapshot, including CSV-only exports
                # whose filename fields may both be blank.
                rows = list(reader)
        # Prevent spreadsheet formulas in a filename; normal filenames are exact.
        if row["original_filename"].lstrip().startswith(("=", "+", "-", "@")):
            row = dict(row, original_filename="'" + row["original_filename"])
        fd, name = tempfile.mkstemp(prefix=".csv_", suffix=".tmp", dir=folder)
        temporary = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, manifest)
        except PermissionError:
            # Keep Excel's open file intact and publish a complete new CSV.
            manifest = folder / ("metadata_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".csv")
            os.rename(temporary, manifest)
        temporary = None
        return manifest
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


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


def _rgb_tile(slide, x, y, tile_size, boxes):
    with slide.read_region((x, y), 0, (tile_size, tile_size)) as region:
        rgba = np.asarray(region)
        # Flatten transparency on white; never retain hidden transparent RGB.
        if np.all(rgba[:, :, 3] == 255):
            rgb = rgba[:, :, :3].copy()
        else:
            alpha = rgba[:, :, 3:4].astype(np.uint16)
            rgb = ((rgba[:, :, :3].astype(np.uint16) * alpha +
                    255 * (255 - alpha) + 127) // 255).astype(np.uint8)
    width, height = slide.dimensions
    if x + tile_size > width:
        rgb[:, max(0, width - x):] = 255
    if y + tile_size > height:
        rgb[max(0, height - y):, :] = 255
    for rx, ry, rw, rh in boxes:
        left = max(0, rx - x)
        top = max(0, ry - y)
        right = min(tile_size, rx + rw - x)
        bottom = min(tile_size, ry + rh - y)
        if right > left and bottom > top:
            rgb[top:bottom, left:right] = 255
    return rgb


def _jpeg_header(data, *, height=None):
    """Whitelist baseline JPEG coding headers, removing APP/COM metadata.

    Return sanitized header through SOS and the original entropy offset.
    Reject unfamiliar markers rather than silently retaining opaque metadata.
    """
    if data[:2] != b"\xff\xd8":
        raise ValueError("JPEG SOI missing")
    result = bytearray(data[:2])
    pos = 2
    frame = None
    restart = 0
    while pos < len(data):
        if data[pos] != 255 or pos + 4 > len(data):
            raise ValueError("Invalid JPEG header")
        marker = data[pos + 1]
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        end = pos + 2 + length
        if length < 2 or end > len(data):
            raise ValueError("Truncated JPEG header")
        segment = bytearray(data[pos:end])
        if marker == 0xC0:
            if frame is not None or length != 17 or segment[4] != 8 or segment[9] != 3:
                raise ValueError("Only baseline 8-bit three-component JPEG is supported")
            frame = (int.from_bytes(segment[5:7], "big"), int.from_bytes(segment[7:9], "big"),
                     tuple(segment[11:18:3]))
            if height is not None:
                segment[5:7] = struct.pack(">H", height)
        elif marker == 0xDD:
            if length != 4:
                raise ValueError("Invalid JPEG restart interval")
            restart = int.from_bytes(segment[4:6], "big")
        elif marker == 0xDA:
            if frame is None or length != 12 or segment[4] != 3 or segment[-3:] != b"\x00\x3f\x00":
                raise ValueError("Only single-scan baseline JPEG is supported")
        elif marker not in (0xDB, 0xC4) and not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            raise ValueError("Unsupported JPEG header marker")
        if not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            result.extend(segment)
        pos = end
        if marker == 0xDA:
            return bytes(result), pos, frame, restart
    raise ValueError("JPEG scan missing")


def _jpeg_entropy(data, *, restart_segment=False):
    """Keep only entropy-coded bytes; require a terminal EOI/restart marker."""
    pos = 0
    while True:
        pos = data.find(b"\xff", pos)
        if pos < 0 or pos + 1 >= len(data):
            raise ValueError("JPEG end marker missing")
        code = data[pos + 1]
        if code == 0 or (not restart_segment and 0xD0 <= code <= 0xD7):
            pos += 2
            continue
        if code == 0xD9 or (restart_segment and 0xD0 <= code <= 0xD7):
            if restart_segment and pos + 2 != len(data):
                raise ValueError("Unexpected bytes after NDPI restart segment")
            return data[:pos]
        raise ValueError("Unsupported marker inside JPEG scan")


def _preserve_jpeg(source, target, dimensions, mpp, emit):
    """Repackage JPEG coding data, never invoke an encoder.

    tifffile exposes NDPI restart segments as virtual MCU-row tiles. Group
    whole segments vertically to satisfy TIFF's multiple-of-16 tile constraint.
    Reset restart numbering in each new JPEG; preserve all entropy bytes.
    """
    import imagecodecs

    with tifffile.TiffFile(source) as original:
        page = original.pages[0]
        width, height = dimensions[0]
        if (page.imagewidth, page.imagelength) != (width, height):
            raise ValueError("Primary TIFF page does not match OpenSlide level 0")
        if page.compression != 7 or page.photometric != 6 or page.planarconfig != 1 or page.jpegtables:
            raise ValueError("Compression preservation requires self-contained baseline YCbCr JPEG; no automatic recompression")
        if not page.is_tiled:
            raise ValueError("Source has no supported JPEG tile/restart layout")
        tw, th = page.tilewidth, page.tilelength
        ndpi = bool(page.is_ndpi)
        group = 1
        header = None
        if ndpi:
            if not page.jpegheader:
                raise ValueError("NDPI restart index/header is required for compression preservation")
            group = 16 // math.gcd(16, th)
            header, _, frame, restart = _jpeg_header(page.jpegheader, height=th * group)
            mcu_w = max(s >> 4 for s in frame[2]) * 8
            mcu_h = max(s & 15 for s in frame[2]) * 8
            if frame[:2] != (th, tw) or th != mcu_h or tw != restart * mcu_w:
                raise ValueError("Unsupported NDPI restart geometry")
            if width % tw or height % (th * group):
                raise ValueError("NDPI edge geometry cannot be preserved without re-encoding")
        if tw % 16 or (th * group) % 16 or max(tw, th * group) > 65535:
            raise ValueError("JPEG tile dimensions are not compatible with standard TIFF")
        if tw * th * group > 16 * 1024**2:
            raise ValueError("JPEG tile is too large for bounded-memory verification")
        cols, rows = math.ceil(width / tw), math.ceil(height / th)
        if len(page.dataoffsets) != cols * rows:
            raise ValueError("Incomplete source JPEG tile index")
        total = cols * math.ceil(rows / group)
        # NDPI headers are repeated for each output tile. No raw-RGB disk reserve.
        required = sum(page.databytecounts) + total * (len(header or b"") + 64) + 16 * 1024**2
        if shutil.disk_usage(target.parent).free < required:
            raise OSError("Not enough space for compressed TIFF export")
        digest = hashlib.sha256()
        sampling = None
        stream = original.filehandle

        def read(index):
            size = page.databytecounts[index]
            if size <= 0 or size > 64 * 1024**2:
                raise ValueError("Missing or oversized JPEG segment")
            offset = page.dataoffsets[index]
            if offset < 0 or offset + size > source.stat().st_size:
                raise ValueError("JPEG segment is outside source file")
            stream.seek(offset)
            data = stream.read(size)
            if len(data) != size:
                raise ValueError("Truncated source JPEG segment")
            return data

        def clean_tile(row, col):
            nonlocal sampling
            if ndpi:
                pieces = [header]
                for j in range(group):
                    data = read((row + j) * cols + col)
                    pieces.append(_jpeg_entropy(data, restart_segment=True))
                    pieces.append(bytes((255, 0xD0 + j % 8)) if j + 1 < group else b"\xff\xd9")
                return b"".join(pieces)
            data = read(row * cols + col)
            clean, start, frame, _ = _jpeg_header(data)
            if frame[:2] != (th, tw):
                raise ValueError("JPEG dimensions disagree with tile dimensions")
            current = frame[2]
            if current[1:] != (0x11, 0x11) or current[0] not in (0x11, 0x21, 0x22):
                raise ValueError("Unsupported JPEG component sampling")
            if sampling is not None and current != sampling:
                raise ValueError("JPEG sampling changes between tiles")
            sampling = current
            return clean + _jpeg_entropy(data[start:]) + b"\xff\xd9"

        first = clean_tile(0, 0)
        if ndpi:
            sampling = frame[2]
            if sampling != (0x11, 0x11, 0x11):
                raise ValueError("Unsupported NDPI component sampling")
        subsampling = (sampling[0] >> 4, sampling[0] & 15)

        def tiles():
            index = 0
            for row in range(0, rows, group):
                for col in range(cols):
                    emit("write", index, total)
                    data = first if index == 0 else clean_tile(row, col)
                    digest.update(struct.pack("<Q", len(data)))
                    digest.update(data)
                    yield data
                    index += 1
            emit("write", total, total)

        with tifffile.TiffWriter(target, bigtiff=True) as writer:
            writer.write(tiles(), shape=(height, width, 3), dtype=np.uint8,
                         tile=(th * group, tw), photometric="ycbcr", compression="jpeg",
                         subsampling=subsampling, metadata=None, description=None,
                         software=False, datetime=False, subfiletype=0,
                         resolution=None if mpp is None else (10000 / mpp[0], 10000 / mpp[1]),
                         resolutionunit="CENTIMETER" if mpp else "NONE")
        expected = digest.digest()

    digest = hashlib.sha256()
    with tifffile.TiffFile(target) as output:
        if len(output.pages) != 1 or not output.is_bigtiff:
            raise ValueError("Unexpected output TIFF structure")
        page = output.pages[0]
        allowed = {254, 256, 257, 258, 259, 262, 277, 282, 283, 284, 296,
                   322, 323, 324, 325, 530, 532}
        if set(page.tags.keys()) - allowed or any(int(t.dtype) == 2 for t in page.tags.values()):
            raise ValueError("Unexpected output metadata")
        if page.shape != (height, width, 3) or len(page.dataoffsets) != total or not page.is_tiled:
            raise ValueError("Output dimensions/tile count changed")
        for i, (offset, count) in enumerate(zip(page.dataoffsets, page.databytecounts)):
            emit("verify", i, total)
            output.filehandle.seek(offset)
            data = output.filehandle.read(count)
            digest.update(struct.pack("<Q", len(data)))
            digest.update(data)
            decoded = imagecodecs.jpeg_decode(data)
            if decoded.shape != (th * group, tw, 3):
                raise ValueError("Output JPEG decode failed")
        if digest.digest() != expected:
            raise ValueError("Output compressed data changed during writing")
        emit("verify", total, total)
    return total


def anonymize_wsi(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    run_id: str | None = None,
    compression: str = "preserve",
    export_image: bool = True,
    export_csv: bool = True,
    include_filename: bool = True,
    redactions: Sequence[Sequence[int]] = (),
    pixels_reviewed: bool = False,
    preserve_mpp: bool = True,
    tile_size: int = 512,
    workers: int = 4,
    progress: Callable[[dict], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Export the highest-resolution image as a single-page TIFF.

    output_dir: base directory; default is input's parent/output. A timestamp
        subdirectory contains anonymous_<uuid>.tiff and metadata.csv.
    run_id: YYYYMMDD_HHMMSS_ffffff timestamp; share between sequential calls to put
        a batch in one directory/CSV. Omit to create a fresh run per call.
    compression: 'preserve' (default) copies JPEG coding data without encoding.
        Supports self-contained baseline YCbCr JPEG TIFF tiles and indexed NDPI
        with 1x1 component sampling, full restart rows, and compatible geometry.
        Other layouts raise ValueError. 'lossless' explicitly uses RGB/Deflate.
    export_image, export_csv: choose TIFF, CSV, or both (default). At least one
        must be True. CSV-only mode reads technical metadata without conversion
        or pixel validation; output_path is None. Without CSV, csv_path is None.
    include_filename: include the original basename in CSV (default True).
        False leaves that field empty; output TIFF names remain anonymous.
    redactions: (x, y, width, height), painted white; requires 'lossless' mode.
    pixels_reviewed: caller confirms no identifiers remain outside supplied masks.
    preserve_mpp: copy only finite positive numeric microns-per-pixel calibration.
    tile_size, workers: control the explicit 'lossless' path only; preserve mode
        retains source coding geometry (apart from NDPI restart regrouping).
    progress: receives {stage, completed, total, percent}; no source identifiers.
    cancelled: cooperative callback evaluated between tiles; True aborts export.

    Preserve mode removes JPEG APP/COM metadata, retains entropy-coded data and
    coding tables, and reconstructs only structural JPEG headers/restart markers
    where required. Verifies every output compressed tile by SHA-256 and decodes
    every tile. Also compares source/output pixels in 25 regions with OpenSlide.
    Source padding pixels are retained; masks require explicit lossless mode.
    Lossless mode verifies every decoded tile against the supplied RGB pixels.
    Both exclude ICC, descriptions, associated images and unreferenced file data.
    Removing ICC can change color-managed appearance. Pixel review is a caller
    assertion, not an automated anonymity certification.

    Uses bounded tile buffers; final publication happens only after validation.
    The input must remain unchanged throughout export (including sidecar files).
    Returns a JSON-serializable report and writes a UTF-8 BOM CSV with the original
    filename and a fixed whitelist of technical fields. A filename can itself
    contain identifiers; the caller explicitly requests this mapping. No patient
    tags, scan dates, scanner IDs or free-text metadata are collected. Filenames
    starting with spreadsheet formula characters are prefixed with an apostrophe.
    """
    source = Path(input_path).expanduser().resolve(strict=True)
    if not all(isinstance(v, bool) for v in (export_image, export_csv, include_filename)):
        raise TypeError("Export options must be boolean")
    if not export_image and not export_csv:
        raise ValueError("Select TIFF image or CSV information to export")
    if not source.is_file():
        raise ValueError("Input must be a WSI file")
    base = Path(output_dir).expanduser().resolve() if output_dir is not None else source.parent / "output"
    if base.exists() and not base.is_dir():
        raise NotADirectoryError("output_dir must be a directory, not a TIFF filename")
    if not isinstance(tile_size, int) or tile_size < 128 or tile_size > 2048 or tile_size % 16:
        raise ValueError("tile_size must be a multiple of 16 between 128 and 2048")
    if not isinstance(workers, int) or not 1 <= workers <= 16:
        raise ValueError("workers must be between 1 and 16")
    if not isinstance(pixels_reviewed, bool):
        raise TypeError("pixels_reviewed must be a boolean")
    if compression not in ("preserve", "lossless"):
        raise ValueError("compression must be preserve or lossless")
    if compression == "preserve" and redactions:
        raise ValueError("Pixel redactions require compression=lossless; preserve mode never re-encodes")
    openslide, dll = _openslide()
    temporary = None
    last_progress = [None]

    def emit(stage, completed, total):
        if cancelled is not None and cancelled():
            raise ExportCancelled("Export cancelled")
        if progress is not None:
            base, scale = (0, 70) if stage == "write" else (70, 30)
            percent = round(base + scale * completed / max(1, total), 1)
            if last_progress[0] != (stage, percent):
                last_progress[0] = (stage, percent)
                progress({"stage": stage, "completed": completed, "total": total,
                          "percent": percent})

    try:
        stat_before = source.stat()
        with openslide.OpenSlide(str(source)) as slide:
            dimensions = [slide.dimensions]
            downsamples = [1.0]
            source_level_count = slide.level_count
            source_mpp = (_numeric_property(slide, "openslide.mpp-x"),
                          _numeric_property(slide, "openslide.mpp-y"))
            objective = _numeric_property(slide, "openslide.objective-power")
            if any(w <= 0 or h <= 0 for w, h in dimensions):
                raise ValueError("Invalid image dimensions")
            if any(not math.isfinite(d) or d < 1 for d in downsamples):
                raise ValueError("Invalid image pyramid")
            boxes = _rectangles(redactions, *dimensions[0])
            mpp = None
            if preserve_mpp and all(v is not None for v in source_mpp):
                mpp = source_mpp
            tiles_per_level = [math.ceil(w / tile_size) * math.ceil(h / tile_size)
                               for w, h in dimensions]
            total = sum(tiles_per_level)
            folder = _run_folder(base, run_id)
            target = folder / ("anonymous_" + uuid.uuid4().hex + ".tiff")
            if not export_image:
                emit("write", 0, 1)
                row = {
                    "original_filename": source.name if include_filename else "",
                    "source_format": source.suffix.lower(),
                    "mpp_x_um": source_mpp[0], "mpp_y_um": source_mpp[1],
                    "width_px": dimensions[0][0], "height_px": dimensions[0][1],
                    "objective_power": objective, "source_level_count": source_level_count,
                    "output_pages": 0, "source_size_bytes": stat_before.st_size,
                    "output_size_bytes": 0, "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "status": "technical_metadata_only", "verified_tiles": 0,
                    "pixel_review_asserted_by_caller": pixels_reviewed,
                }
                emit("verify", 1, 1)
                stat_after = source.stat()
                if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
                    raise ValueError("Input changed during export")
                if cancelled is not None and cancelled():
                    raise ExportCancelled("Export cancelled")
                csv_path = _record_csv(folder, row)
                return {"output_path": None, "directory": str(folder), "csv_path": str(csv_path),
                        "format": "csv-only", "status": "technical_metadata_only",
                        "level_dimensions": [list(d) for d in dimensions], "verified_tiles": 0,
                        "pixel_review_asserted_by_caller": pixels_reviewed, "size_bytes": 0,
                        "compression": None, "mpp": list(source_mpp)}
            fd, name = tempfile.mkstemp(prefix=".wsi_", suffix=".partial.tiff", dir=target.parent)
            os.close(fd)
            temporary = Path(name)
            if compression == "preserve":
                verified = _preserve_jpeg(source, temporary, dimensions, mpp, emit)
            else:
                # Deflate worst-case can approach raw size, including edge padding.
                required = int(total * tile_size * tile_size * 3 * 1.02) + 64 * 1024**2
                if shutil.disk_usage(target.parent).free < required:
                    raise OSError("Not enough space for a worst-case lossless TIFF export")
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
                                    rgb = _rgb_tile(slide, x, y, tile_size, boxes)
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
                        # Parallel segments() batches by COMPRESSED size; on blank
                        # slides that can retain gigabytes of decoded futures.
                        # Decode one tile at a time for a bounded memory footprint.
                        for data, _, _ in page.segments(maxworkers=1, buffersize=8 * 1024**2):
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
                    raise ValueError("Output single-image readback failed")
                if check.properties.get("openslide.vendor") != "generic-tiff":
                    raise ValueError("Output is not a generic tiled TIFF")
                with check.read_region((0, 0), 0, (64, 64)) as region:
                    region.load()
                if compression == "preserve":
                    width, height = dimensions[0]
                    size = (min(256, width), min(256, height))
                    for y in np.linspace(0, height - size[1], 5, dtype=int):
                        for x in np.linspace(0, width - size[0], 5, dtype=int):
                            if cancelled is not None and cancelled():
                                raise ExportCancelled("Export cancelled")
                            with slide.read_region((int(x), int(y)), 0, size) as a, \
                                    check.read_region((int(x), int(y)), 0, size) as b:
                                if not np.array_equal(np.asarray(a), np.asarray(b)):
                                    raise ValueError("Source/output sampled pixels differ")
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
            result = {
                "output_path": str(target), "directory": str(folder), "format": "single-page-bigtiff",
                "status": "metadata_clean_pixels_reviewed" if pixels_reviewed else "metadata_clean_pixel_review_required",
                "metadata_clean": True, "pixel_review_asserted_by_caller": pixels_reviewed,
                "redaction_count": len(boxes), "level_dimensions": [list(d) for d in dimensions],
                "mpp": list(mpp) if mpp else None, "compression": "jpeg-preserved" if compression == "preserve" else "deflate-lossless",
                "all_output_tiles_verified": True, "verified_tiles": verified,
                "verification": "compressed-sha256-and-all-tiles-decode" if compression == "preserve" else "all-decoded-pixels-sha256",
                "source_output_pixel_regions_verified": 25 if compression == "preserve" else 0,
                "source_metadata_copied": False, "associated_images_copied": False,
                "source_compressed_payload_copied": compression == "preserve",
                "jpeg_app_com_removed": compression == "preserve",
                "reencoded": compression != "preserve", "icc_profile_copied": False,
                "representation": "OpenSlide 2D RGB; not all focal planes/channels",
                "size_bytes": target.stat().st_size,
            }
            row = {
                "original_filename": source.name if include_filename else "", "output_filename": target.name,
                "source_format": source.suffix.lower(), "mpp_x_um": source_mpp[0], "mpp_y_um": source_mpp[1],
                "width_px": dimensions[0][0], "height_px": dimensions[0][1],
                "objective_power": objective, "source_level_count": source_level_count, "output_pages": 1,
                "source_size_bytes": stat_before.st_size, "output_size_bytes": result["size_bytes"],
                "compression": result["compression"], "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": result["status"], "verified_tiles": verified,
                "pixel_review_asserted_by_caller": pixels_reviewed,
            }
            try:
                result["csv_path"] = str(_record_csv(folder, row)) if export_csv else None
            except Exception:
                target.unlink()  # This call's newly created file only.
                raise
            return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if dll is not None:
            dll.close()


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    parser.add_argument("--compression", choices=("preserve", "lossless"), default="preserve")
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
                           pixels_reviewed=args.pixels_reviewed, compression=args.compression, progress=show_progress)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    _main()
