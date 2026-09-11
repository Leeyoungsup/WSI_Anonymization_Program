"""Standalone WSI -> pyramidal TIFF and technical CSV (Python 3.10+).

Copy this file to another project. Dependencies:
    pip install openslide-python "openslide-bin>=4.0.1.2" numpy tifffile imagecodecs Pillow

    from wsi_anonymizer import anonymize_wsi
    result = anonymize_wsi('slide.ndpi', 'output')

The default preserves baseline JPEG coding data from compatible SVS/TIFF tiles
and NDPI restart segments. APP/COM headers, private TIFF tags, associated images,
and unreferenced file bytes are excluded. Unsupported layouts fail explicitly;
they are never silently re-encoded. compression='lossless' explicitly selects
the previous decoded RGB/Deflate path for other OpenSlide-readable inputs/masks.
The default pyramid reuses compatible tissue levels and generates smaller
overviews from sanitized output. The original level 0 is never re-encoded in
preserve mode. This does not export all channels/focal planes of complex inputs.
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
import sys
import subprocess
import threading
import queue
import mmap
import base64
from collections.abc import Callable, Sequence

import numpy as np
import tifffile

__all__ = ["anonymize_wsi", "ExportCancelled"]

PHILIPS_EXTENSIONS = {".isyntax", ".i2syntax"}


class PhilipsSlide:
    """OpenSlide-shaped reader backed by an isolated Python 3.7 SDK process.

    Set PHILIPS_PYTHON to the SDK environment's python.exe, or supply a portable
    philips/PhilipsBridge.exe next to this module/application.
    """
    def __init__(self, path, cancelled=None):
        if os.name != "nt":
            raise ValueError("This Philips bridge requires Windows x64")
        self._cancelled = cancelled
        self._process = None
        root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        helper = root / "philips" / "PhilipsBridge.exe"
        portable_python = root / "philips" / "python.exe"
        configured = os.environ.get("PHILIPS_PYTHON")
        python = Path(configured) if configured else Path.home() / ".conda/envs/philips-sdk-py37/python.exe"
        script = Path(__file__).resolve().parent / "philips_bridge/export_server.py"
        if helper.is_file() and not configured:
            command = [str(helper)]
        elif portable_python.is_file() and not configured:
            command = [str(portable_python), "-I", "-u", str(root / "philips/bridge/export_server.py")]
        elif python.is_file() and script.is_file():
            command = [str(python), "-u", str(script)]
        else:
            raise ValueError("Philips SDK reader is missing. Install the Python 3.7 SDK environment and set PHILIPS_PYTHON, or use the Philips-enabled release.")
        env = os.environ.copy()
        for key in ("PYTHONHOME", "PYTHONPATH", "CONDA_PREFIX", "_MEIPASS2"):
            env.pop(key, None)
        env["PYTHONNOUSERSITE"] = "1"
        self._scratch = tempfile.TemporaryDirectory(prefix="wsi_philips_")
        env["WSI_PHILIPS_SCRATCH"] = self._scratch.name
        self._messages = queue.Queue()
        try:
            self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except BaseException:
            self._scratch.cleanup()
            raise
        process = self._process
        def receive():
            try:
                for line in process.stdout:
                    self._messages.put(line)
            except (OSError, ValueError):
                pass
            finally:
                self._messages.put(None)
        threading.Thread(target=receive, daemon=True).start()
        try:
            data = self._request({"command": "open", "path": str(Path(path).resolve())})
            self.dimensions = tuple(data["dimensions"])
            self.level_dimensions = tuple(tuple(d) for d in data["level_dimensions"])
            self.level_downsamples = tuple(data["level_downsamples"])
            self.level_count = len(self.level_dimensions)
            self.properties = data["properties"]
            self.associated_images = dict.fromkeys(data["associated_images"])
            self.icc = base64.b64decode(data["icc"], validate=True) if data["icc"] else None
            self.display_origin = data["display_origin"]
        except BaseException:
            self.close()
            raise

    def _request(self, message, progress=None):
        import time
        try:
            self._process.stdin.write(json.dumps(message, ensure_ascii=True) + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError):
            raise ValueError("Philips SDK process stopped") from None
        deadline = time.monotonic() + 120
        while True:
            if self._cancelled and self._cancelled():
                raise ExportCancelled("Export cancelled")
            if time.monotonic() > deadline:
                raise ValueError("Philips SDK response timed out")
            try:
                line = self._messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                raise ValueError("Philips SDK process stopped; check its Python 3.7 runtime and SDK dependencies")
            try:
                response = json.loads(line)
            except ValueError:
                continue  # Discard native diagnostic text, never persist it.
            if response.get("event") == "native_progress" and progress is not None:
                progress(response["stage"], response["completed"], response["total"])
                deadline = time.monotonic() + 120
                continue
            if not response.get("ok"):
                raise ValueError("Philips SDK could not read this file/region. The file may be damaged or unsupported by SDK 2.0.")
            return response.get("data", {})

    def read_region(self, location, level, size):
        from PIL import Image
        width, height = map(int, size)
        if not (0 < width <= 4096 and 0 < height <= 4096):
            raise ValueError("Philips region exceeds bounded buffer")
        name = "Local\\wsi_" + uuid.uuid4().hex
        count = width * height * 4
        with mmap.mmap(-1, count, tagname=name) as memory:
            reply = self._request({"command": "region", "location": list(map(int, location)),
                "level": int(level), "size": [width, height], "memory": name})
            if reply["bytes"] != count:
                raise ValueError("Philips SDK returned an unexpected pixel buffer")
            image = Image.frombytes("RGBA", (width, height), memory[:])
        if self.icc:
            image.info["icc_profile"] = self.icc
        return image

    def get_best_level_for_downsample(self, scale):
        return max((i for i, d in enumerate(self.level_downsamples) if d <= scale), default=0)

    def get_thumbnail(self, size):
        from PIL import Image
        level = self.get_best_level_for_downsample(max(self.dimensions[0]/size[0], self.dimensions[1]/size[1]))
        while max(self.level_dimensions[level]) > 4096 and level < self.level_count - 1:
            level += 1
        with self.read_region((0, 0), level, self.level_dimensions[level]) as region:
            result = region.convert("RGB")
            result.thumbnail(size, Image.Resampling.LANCZOS)
        return result

    def close(self):
        process = self._process
        if process is not None:
            try:
                process.stdin.close()  # EOF lets the server release the SDK.
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait()
            finally:
                process.stdout.close()
                self._process = None
                self._scratch.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _open_slide(path, openslide, cancelled=None):
    return PhilipsSlide(path, cancelled) if Path(path).suffix.lower() in PHILIPS_EXTENSIONS else openslide.OpenSlide(str(path))

CSV_FIELDS = (
    "original_filename", "output_filename", "source_format", "mpp_x_um", "mpp_y_um",
    "width_px", "height_px", "objective_power", "source_level_count", "output_pages",
    "source_size_bytes", "output_size_bytes", "compression", "exported_at",
    "status", "verified_tiles", "pixel_review_asserted_by_caller",
    "physical_width_mm", "physical_height_mm",
    "source_vendor", "icc_profile_copied", "icc_review_required",
    "anonymization_audit",
    "source_representation", "source_origin_x_px", "source_origin_y_px",
)


def _numeric_property(slide, key):
    try:
        value = slide.properties.get(key)
        if value is None and key in ("openslide.mpp-x", "openslide.mpp-y"):
            data = _read_technical_description(slide.properties.get("tiff.ImageDescription", ""))
            value = data.get("mpp_x_um" if key.endswith("-x") else "mpp_y_um")
        if isinstance(value, bool):
            return None
        value = float(value)
        return value if math.isfinite(value) and 0.000001 <= value <= 100000 else None
    except (KeyError, ValueError, TypeError):
        return None


def _read_technical_description(description):
    try:
        if description.startswith("Aperio compatible WSI Anonymization|"):
            description = description.split("|WSI_Technical=", 1)[1]
        data = json.loads(description)
        return data if isinstance(data, dict) and data.get("schema") == "wsi-technical-v1" else {}
    except (ValueError, TypeError, IndexError):
        return {}


def _technical_description(data):
    parts = ["Aperio compatible WSI Anonymization"]
    if data["objective_power"] is not None:
        parts.append(f"AppMag={data['objective_power']:.17g}")
    x, y = data["mpp_x_um"], data["mpp_y_um"]
    if x is not None and x == y:
        parts.append(f"MPP={x:.17g}")
    parts.append("WSI_Technical=" + json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return "|".join(parts)


def _objective_power(slide):
    value = _numeric_property(slide, "openslide.objective-power")
    if value is not None:
        return value
    try:
        data = _read_technical_description(slide.properties.get("tiff.ImageDescription", ""))
        if data.get("schema") != "wsi-technical-v1":
            return None
        value = data.get("objective_power")
        if type(value) in (int, float) and math.isfinite(value) and 0.000001 <= value <= 100000:
            return float(value)
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def _inventory(path, slide=None):
    """Record tag IDs/presence only. Never record original metadata values."""
    data = {"tiff_checked": False, "tags": [], "text_tags": [], "associated": []}
    if slide is not None:
        data["associated"] = [name if name in ("label", "macro", "thumbnail") else "other"
                              for name in slide.associated_images]
    try:
        with tifffile.TiffFile(path) as tif:
            data["tags"] = sorted({tag.code for page in tif.pages for tag in page.tags.values()})
            data["text_tags"] = sorted({tag.code for page in tif.pages for tag in page.tags.values() if int(tag.dtype) == 2})
            data["tiff_checked"] = True
    except tifffile.TiffFileError:
        pass
    return data


def _removal_audit(before, after, *, rename_output, include_filename, export_csv, icc, reviewed):
    source, output = set(before["tags"]), set(after["tags"])
    checked = before["tiff_checked"] and after["tiff_checked"]
    entries = []
    for name, code in (("description", 270), ("software", 305), ("datetime", 306),
                       ("document_name", 269), ("artist", 315), ("host", 316), ("icc", 34675)):
        status = "not_checked" if not checked else "not_present" if code not in source else (
            "removed" if code not in output else "retained" if name == "icc" else "rewritten")
        entries.append({"item": name, "status": status, "tag_code": code,
                        "before": "unknown" if not checked else "present" if code in source else "absent",
                        "after": "technical_metadata" if name == "description" and code in output else
                                 "present" if code in output else "absent"})
    for name in ("label", "macro", "thumbnail", "other"):
        count = before["associated"].count(name)
        entries.append({"item": name, "status": "removed" if count else "not_present", "count": count,
                        "before": "present" if count else "absent", "after": "absent"})
    entries.extend([
        {"item": "filename", "status": "renamed" if rename_output else "retained",
         "before": "source_filename", "after": "anonymous_filename" if rename_output else "source_stem_tiff"},
        {"item": "csv_filename", "status": "not_exported" if not export_csv else "retained" if include_filename else "excluded",
         "before": "source_filename", "after": "not_exported" if not export_csv else "source_filename" if include_filename else "empty"},
        {"item": "pixels", "status": "user_reviewed" if reviewed else "review_required",
         "before": "not_assessed", "after": "user_reviewed" if reviewed else "review_required"},
        {"item": "icc_review", "status": "review_required" if icc else "not_applicable",
         "before": "not_assessed", "after": "review_required" if icc else "not_applicable"},
        {"item": "jpeg_app_com", "status": "excluded_by_policy", "before": "not_counted", "after": "excluded_by_policy"},
    ])
    return {"scope": "top-level TIFF tag IDs and OpenSlide associated images; no patient-field detection",
            "entries": entries, "tag_comparison_available": checked,
            "removed_tag_codes": sorted(source - output) if checked else [],
            "removed_text_tag_codes": sorted(set(before["text_tags"]) - output) if checked else [],
            "output_tag_codes": sorted(output)}


def _source_vendor(slide):
    allowed = {"aperio", "hamamatsu", "leica", "mirax", "philips", "sakura", "trestle",
               "ventana", "zeiss", "dicom", "generic-tiff", "synthetic", "argos", "huron"}
    stored = _read_technical_description(slide.properties.get("tiff.ImageDescription", "")).get("source_vendor")
    if isinstance(stored, str) and stored in allowed:
        return stored
    vendor = slide.properties.get("openslide.vendor")
    return vendor if vendor in allowed else None


def _technical_metadata(dimensions, mpp, objective, source_vendor=None):
    width, height = dimensions
    x, y = mpp if mpp is not None else (None, None)
    return {"schema": "wsi-technical-v1", "objective_power": objective, "source_vendor": source_vendor,
            "width_px": width, "height_px": height, "mpp_x_um": x, "mpp_y_um": y,
            "physical_width_mm": width * x / 1000 if x is not None else None,
            "physical_height_mm": height * y / 1000 if y is not None else None}


def _validate_metadata(page, allowed, description=None, icc=None):
    permitted = allowed | ({270} if description is not None else set()) | ({34675} if icc else set())
    if set(page.tags.keys()) - permitted:
        raise ValueError("Unexpected output metadata")
    for tag in page.tags.values():
        if int(tag.dtype) == 2 and (tag.code != 270 or description is None or tag.value != description):
            raise ValueError("Unexpected text metadata")
    if description is not None and page.description != description:
        raise ValueError("Technical metadata was not retained")
    if icc and (34675 not in page.tags or page.tags[34675].value != icc):
        raise ValueError("ICC profile verification failed")


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


def _preserve_jpeg(source, target, dimensions, mpp, emit, *, page_index=0, append=False, description=None, icc=None):
    """Repackage JPEG coding data, never invoke an encoder.

    tifffile exposes NDPI restart segments as virtual MCU-row tiles. Group
    whole segments vertically to satisfy TIFF's multiple-of-16 tile constraint.
    Reset restart numbering in each new JPEG; preserve all entropy bytes.
    """
    import imagecodecs

    with tifffile.TiffFile(source) as original:
        page = original.pages[page_index]
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

        with tifffile.TiffWriter(target, bigtiff=True, append=append) as writer:
            writer.write(tiles(), shape=(height, width, 3), dtype=np.uint8,
                         tile=(th * group, tw), photometric="ycbcr", compression="jpeg",
                         subsampling=subsampling, metadata=None, description=description, iccprofile=icc,
                         software=False, datetime=False, subfiletype=1 if append else 0,
                         resolution=None if mpp is None else (10000 / mpp[0], 10000 / mpp[1]),
                         resolutionunit="CENTIMETER" if mpp else "NONE")
        expected = digest.digest()

    digest = hashlib.sha256()
    with tifffile.TiffFile(target) as output:
        if (not append and len(output.pages) != 1) or not output.is_bigtiff:
            raise ValueError("Unexpected output TIFF structure")
        page = output.pages[-1] if append else output.pages[0]
        allowed = {254, 256, 257, 258, 259, 262, 277, 282, 283, 284, 296,
                   322, 323, 324, 325, 530, 532}
        _validate_metadata(page, allowed, description, icc)
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


def _write_jpeg(slide, target, mpp, boxes, tile_size, emit, description, icc):
    """Encode tissue as JPEG Q90, then verify every compressed tile and decode."""
    import imagecodecs
    width, height = slide.dimensions
    total = math.ceil(width / tile_size) * math.ceil(height / tile_size)
    if shutil.disk_usage(target.parent).free < total * tile_size * tile_size * 3 + 64 * 1024**2:
        raise OSError("Not enough space for JPEG TIFF export")
    digest = hashlib.sha256()
    def tiles():
        count = 0
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                emit("write", count, total)
                rgb = _rgb_tile(slide, x, y, tile_size, boxes)
                encoded = imagecodecs.jpeg_encode(rgb, level=90, subsampling=(2, 2))
                header, offset, _, _ = _jpeg_header(encoded)
                encoded = header + _jpeg_entropy(encoded[offset:]) + b"\xff\xd9"
                digest.update(struct.pack("<Q", len(encoded)))
                digest.update(encoded)
                yield encoded
                count += 1
        emit("write", total, total)
    with tifffile.TiffWriter(target, bigtiff=True) as writer:
        writer.write(tiles(), shape=(height, width, 3), dtype=np.uint8, tile=(tile_size, tile_size),
            photometric="ycbcr", compression="jpeg", subsampling=(2, 2),
            metadata=None, description=description, software=False, datetime=False,
            iccprofile=icc, subfiletype=0,
            resolution=None if mpp is None else (10000 / mpp[0], 10000 / mpp[1]),
            resolutionunit="CENTIMETER" if mpp else "NONE")
    expected = digest.digest()
    digest = hashlib.sha256()
    allowed = {254, 256, 257, 258, 259, 262, 277, 282, 283, 284, 296, 322, 323, 324, 325, 530, 532}
    with tifffile.TiffFile(target) as tif:
        if len(tif.pages) != 1 or not tif.is_bigtiff:
            raise ValueError("Unexpected JPEG TIFF structure")
        page = tif.pages[0]
        _validate_metadata(page, allowed, description, icc)
        if len(page.dataoffsets) != total:
            raise ValueError("Missing JPEG tiles")
        for index, (offset, size) in enumerate(zip(page.dataoffsets, page.databytecounts)):
            emit("verify", index, total)
            tif.filehandle.seek(offset)
            data = tif.filehandle.read(size)
            digest.update(struct.pack("<Q", len(data)))
            digest.update(data)
            if imagecodecs.jpeg_decode(data).shape != (tile_size, tile_size, 3):
                raise ValueError("JPEG tile decode failed")
        if digest.digest() != expected:
            raise ValueError("JPEG compressed payload changed")
    emit("verify", total, total)
    return total


def _append_overview(target, openslide, mpp, compression, notify):
    """Append a 4x reduced tiled level from the sanitized output, bounded buffers."""
    import imagecodecs
    from PIL import Image
    tile, factor, halo = 256, 4, 16
    digest = hashlib.sha256()
    with openslide.OpenSlide(str(target)) as parent:
        level = parent.level_count - 1
        pw, ph = parent.level_dimensions[level]
        width, height = math.ceil(pw / factor), math.ceil(ph / factor)
        scale = parent.level_downsamples[level]
        total = math.ceil(width / tile) * math.ceil(height / tile)
        def tiles():
            index = 0
            for y in range(0, height, tile):
                for x in range(0, width, tile):
                    notify(index / total * 0.7)
                    location = (round((x * factor - halo) * scale), round((y * factor - halo) * scale))
                    with parent.read_region(location, level, (tile * factor + 2 * halo,) * 2) as rgba:
                        white = Image.new("RGB", rgba.size, "white")
                        try:
                            white.paste(rgba, mask=rgba.getchannel("A"))
                            with white.resize((tile + 2 * halo // factor,) * 2, Image.Resampling.LANCZOS) as small:
                                with small.crop((halo // factor, halo // factor, tile + halo // factor, tile + halo // factor)) as cropped:
                                    rgb = np.asarray(cropped).copy()
                        finally:
                            white.close()
                    if x + tile > width:
                        rgb[:, max(0, width - x):] = 255
                    if y + tile > height:
                        rgb[max(0, height - y):] = 255
                    if compression in ("preserve", "jpeg"):
                        data = imagecodecs.jpeg_encode(rgb, level=90, subsampling=(2, 2))
                        header, offset, _, _ = _jpeg_header(data)
                        data = header + _jpeg_entropy(data[offset:]) + b"\xff\xd9"
                    elif compression == "jpeg2000":
                        data = imagecodecs.jpeg2k_encode(rgb, reversible=True, codecformat="J2K", mct=True)
                    else:
                        data = imagecodecs.deflate_encode(rgb, level=1)
                    digest.update(struct.pack("<Q", len(data)))
                    digest.update(data)
                    yield data
                    index += 1
        if shutil.disk_usage(target.parent).free < total * tile * tile * 3 + 16 * 1024**2:
            raise OSError("Not enough space for pyramid overview")
        with tifffile.TiffWriter(target, append=True) as writer:
            writer.write(tiles(), shape=(height, width, 3), dtype=np.uint8, tile=(tile, tile),
                         compression="jpeg" if compression in ("preserve", "jpeg") else (33005 if compression == "jpeg2000" else "deflate"),
                         photometric="ycbcr" if compression in ("preserve", "jpeg") else "rgb",
                         subsampling=(2, 2) if compression in ("preserve", "jpeg") else None,
                         metadata=None, description=None, software=False, datetime=False, subfiletype=1,
                         resolution=None if mpp is None else (10000 / (mpp[0] * parent.dimensions[0] / width),
                                                              10000 / (mpp[1] * parent.dimensions[1] / height)),
                         resolutionunit="CENTIMETER" if mpp else "NONE")
    expected = digest.digest()
    digest = hashlib.sha256()
    with tifffile.TiffFile(target) as tif:
        page = tif.pages[-1]
        for index, (offset, size) in enumerate(zip(page.dataoffsets, page.databytecounts)):
            notify(0.7 + 0.3 * index / total)
            tif.filehandle.seek(offset)
            data = tif.filehandle.read(size)
            digest.update(struct.pack("<Q", len(data)))
            digest.update(data)
            if compression in ("preserve", "jpeg"):
                decoded = imagecodecs.jpeg_decode(data)
                if decoded.shape != (tile, tile, 3):
                    raise ValueError("Pyramid JPEG tile decode failed")
            elif compression == "jpeg2000":
                if imagecodecs.jpeg2k_decode(data).shape != (tile, tile, 3):
                    raise ValueError("Pyramid JPEG 2000 tile decode failed")
            elif len(imagecodecs.deflate_decode(data)) != tile * tile * 3:
                raise ValueError("Pyramid Deflate tile decode failed")
        if len(page.dataoffsets) != total or digest.digest() != expected:
            raise ValueError("Pyramid compressed data changed")
    notify(1.0)
    return (width, height), total


def _append_pyramid(source, target, slide, openslide, mpp, compression, emit, description=None, icc=None):
    """Reuse only recognized tissue levels; never copy label/macro/thumbnail IFDs."""
    dimensions = [slide.dimensions]
    candidates = []
    if compression == "preserve":
        with tifffile.TiffFile(source) as tif:
            for index, page in enumerate(tif.pages):
                shape = (page.imagewidth, page.imagelength)
                if index == 0 or shape not in slide.level_dimensions[1:]:
                    continue
                if not page.is_tiled or page.compression != 7 or page.photometric != 6 or page.jpegtables:
                    continue
                if page.is_ndpi:
                    if not page.jpegheader or page.tags[65421].value <= 0:
                        continue
                    if page.imagewidth % page.tilewidth or page.imagelength % 16 or page.tilewidth % 16:
                        continue
                candidates.append((index, shape))
    candidates.sort(key=lambda item: item[1][0], reverse=True)
    end = candidates[-1][1] if candidates else dimensions[0]
    generated_count = 0
    while max(end) > 512:
        end = (math.ceil(end[0] / 4), math.ceil(end[1] / 4))
        generated_count += 1
    steps = len(candidates) + generated_count
    verified = 0
    done = 0
    def notify(fraction):
        emit("pyramid", done + fraction, max(steps, 1))
    for index, shape in candidates:
        if not all(a < b for a, b in zip(shape, dimensions[-1])):
            continue
        scaled_mpp = None if mpp is None else (mpp[0] * dimensions[0][0] / shape[0],
                                               mpp[1] * dimensions[0][1] / shape[1])
        def progress(stage, completed, total):
            notify((0 if stage == "write" else 0.7) + (0.7 if stage == "write" else 0.3) * completed / max(total, 1))
        verified += _preserve_jpeg(source, target, [shape], scaled_mpp, progress, page_index=index, append=True)
        dimensions.append(shape)
        done += 1
    preserved = len(dimensions)
    while max(dimensions[-1]) > 512:
        shape, tiles = _append_overview(target, openslide, mpp, compression, notify)
        verified += tiles
        dimensions.append(shape)
        done += 1
    allowed = {254, 256, 257, 258, 259, 262, 277, 282, 283, 284, 296, 322, 323, 324, 325, 530, 532}
    with tifffile.TiffFile(target) as tif:
        if len(tif.pages) != len(dimensions):
            raise ValueError("Unexpected pyramid page count")
        for index, page in enumerate(tif.pages):
            _validate_metadata(page, allowed, description if index == 0 else None, icc if index == 0 else None)
            if (not page.is_tiled or page.subifds or page.subfiletype != (1 if index else 0)
                    or (page.imagewidth, page.imagelength) != dimensions[index]):
                raise ValueError("Invalid pyramid structure or unexpected metadata")
    emit("pyramid", 1, 1)
    return dimensions, verified, preserved if compression == "preserve" else 0, len(dimensions) - preserved


def _export_philips_native(source, base, run_id, export_csv, include_filename,
                           rename_output, reviewed, preserve_icc, workers, progress, cancelled):
    """Publish a rebuilt iSyntax only after native block and metadata verification."""
    temporary = None
    def emit(stage, completed, total):
        if cancelled and cancelled():
            raise ExportCancelled("Export cancelled")
        percent = (0 if stage == "write" else 60) + (60 if stage == "write" else 39) * completed / max(1, total)
        if progress:
            progress({"stage": stage, "completed": completed, "total": total, "percent": percent})
    try:
        emit("write", 0, 1)
        before = source.stat()
        with PhilipsSlide(source, cancelled) as slide:
            icc = slide.icc if preserve_icc else None
            if icc and (len(icc) > 64 * 1024**2 or icc[16:20] != b"RGB "):
                raise ValueError("Only bounded RGB ICC profiles can be preserved")
            folder = _run_folder(base, run_id)
            if shutil.disk_usage(folder).free < before.st_size + 64 * 1024**2:
                raise OSError("Not enough space for native Philips export")
            fd, name = tempfile.mkstemp(prefix=".wsi_", suffix=".partial.isyntax", dir=folder)
            os.close(fd)
            temporary = Path(name)
            native = slide._request({"command": "export_native", "path": str(temporary),
                "preserve_icc": preserve_icc, "workers": workers}, progress=emit)
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Input changed during native export")
            emit("verify", 1, 1)
            mpp = [_numeric_property(slide, "openslide.mpp-x"), _numeric_property(slide, "openslide.mpp-y")]
            technical = _technical_metadata(slide.dimensions, mpp, None, "philips")
            technical.update(source_representation="Philips native compressed tissue blocks",
                             source_origin_x_px=slide.display_origin[0], source_origin_y_px=slide.display_origin[1])
            audit = _removal_audit(_inventory(source, slide), _inventory(temporary),
                rename_output=rename_output, include_filename=include_filename,
                export_csv=export_csv, icc=icc, reviewed=reviewed)
            audit["scope"] = "New iSyntax XML field whitelist; original tissue blocks preserved; source XML excluded"
            audit["entries"] = [e for e in audit["entries"] if e["item"] != "jpeg_app_com" and "tag_code" not in e]
            audit["entries"].append({"item": "icc", "status": "retained" if icc else "excluded_by_policy",
                "before": "present" if slide.icc else "absent", "after": "present" if icc else "absent"})
            for entry in audit["entries"]:
                if entry["item"] == "filename" and not rename_output:
                    entry["after"] = "source_stem_isyntax"
            audit["entries"].append({"item": "philips_metadata", "status": "rewritten",
                "before": "not_assessed", "after": "technical_metadata"})
            status = ("icc_review_required_" if icc else "metadata_clean_") + (
                "pixels_reviewed" if reviewed else "pixel_review_required")
            stem = "anonymous_" + uuid.uuid4().hex if rename_output else source.stem
            target = folder / (stem + ".isyntax")
            suffix = 1
            while True:
                try:
                    os.rename(temporary, target)  # Windows: atomic and refuses overwrite.
                    break
                except FileExistsError:
                    if rename_output:
                        raise
                    suffix += 1
                    target = folder / (stem + "_" + str(suffix) + ".isyntax")
            temporary = None
            dimensions = native["level_dimensions"]
            result = {
                "output_path": str(target), "directory": str(folder), "format": "philips-isyntax",
                "pyramid": True, "preserved_levels": len(dimensions), "generated_levels": 0,
                "thumbnail_verified": False, "status": status, "metadata_clean": not bool(icc),
                "icc_review_required": bool(icc), "pixel_review_asserted_by_caller": reviewed,
                "redaction_count": 0, "level_dimensions": dimensions, "objective_power": None,
                "rename_output": rename_output, "technical_metadata": technical, "anonymization_audit": audit,
                "mpp": mpp, "compression": "philips-native-preserved", "additional_lossy_compression": False,
                "jpeg_quality": None, "verified_tiles": native["verified_blocks"],
                "all_output_tiles_verified": False, "all_compressed_blocks_verified": True,
                "verification": "all-native-blocks-byte-identical-and-sampled-sdk-decode",
                "source_output_pixel_regions_verified": native["sampled_regions_decoded"] if preserve_icc else 0,
                "source_metadata_copied": False, "associated_images_copied": False,
                "source_compressed_payload_copied": True, "jpeg_app_com_removed": False,
                "reencoded": False, "base_image_reencoded": False, "icc_profile_copied": bool(icc),
                "icc_profile_bytes": len(icc) if icc else 0, "source_vendor": "philips",
                "representation": "Original Philips tissue coding; display appearance depends on retained ICC",
                "philips_display_origin": slide.display_origin, "native_validation": native,
                "size_bytes": target.stat().st_size,
            }
            row = {**technical, "original_filename": source.name if include_filename else "",
                "output_filename": target.name, "source_format": source.suffix.lower(),
                "mpp_x_um": mpp[0], "mpp_y_um": mpp[1], "source_level_count": slide.level_count,
                "output_pages": len(dimensions), "source_size_bytes": before.st_size,
                "output_size_bytes": result["size_bytes"], "compression": result["compression"],
                "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"), "status": status,
                "verified_tiles": native["verified_blocks"], "icc_profile_copied": bool(icc),
                "icc_review_required": bool(icc), "pixel_review_asserted_by_caller": reviewed,
                "anonymization_audit": json.dumps(audit, ensure_ascii=True, separators=(",", ":"))}
            try:
                result["csv_path"] = str(_record_csv(folder, row)) if export_csv else None
            except Exception:
                target.unlink()
                raise
            return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def anonymize_wsi(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    run_id: str | None = None,
    compression: str = "preserve",
    pyramid: bool = True,
    export_image: bool = True,
    export_csv: bool = True,
    include_filename: bool = True,
    rename_output: bool = True,
    redactions: Sequence[Sequence[int]] = (),
    pixels_reviewed: bool = False,
    preserve_mpp: bool = True,
    preserve_icc: bool = False,
    tile_size: int = 512,
    workers: int = 4,
    progress: Callable[[dict], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Export tissue as TIFF, or native iSyntax with compression='philips'.

    compression='philips': Philips iSyntax/i2syntax only. Rebuild a new .isyntax
        container with whitelisted technical XML and original compressed WSI blocks.
        No re-encoding, labels or macros. Requires pyramid=True, preserve_mpp=True
        and no redactions. The original tissue levels/calibration are retained.
        ICC is optional; excluding it can change SDK-rendered colors despite exact
        native compressed-block preservation. OpenSlide cannot read native iSyntax;
        use PhilipsSlide/the bundled SDK. All compressed blocks are compared, but
        only sampled image regions are decoded (explicitly reported).

    output_dir: base directory; default is input's parent/output. A timestamp
        subdirectory contains anonymous_<uuid>.tiff and metadata.csv.
    run_id: YYYYMMDD_HHMMSS_ffffff timestamp; share between sequential calls to put
        a batch in one directory/CSV. Omit to create a fresh run per call.
    compression: 'jpeg2000' saves decoded RGB losslessly using reversible JPEG 2000
        in Aperio-compatible TIFF (compression tag 33005), including generated levels.
        Philips uses SDK display RGB, not the original internal representation.
    compression: 'preserve' (default) copies JPEG coding data without encoding.
        Supports self-contained baseline YCbCr JPEG TIFF tiles and indexed NDPI
        with 1x1 component sampling, full restart rows, and compatible geometry.
        Other layouts raise ValueError. 'lossless' explicitly uses RGB/Deflate.
        'jpeg' explicitly re-encodes SDK/OpenSlide RGB at JPEG quality 90, 4:2:0.
        It adds lossy compression; it does not preserve Philips iSyntax coding.
    pyramid: True by default. Reuse compatible source tissue levels in preserve
        mode, then generate 4x overviews down to <=512 pixels on the longest edge.
        Additional TIFF overviews use the selected codec (JPEG Q90 in preserve mode).
        Base pixels are not re-encoded in preserve mode. False exports level 0 only.
    export_image, export_csv: choose TIFF, CSV, or both (default). At least one
        must be True. CSV-only mode reads technical metadata without conversion
        or pixel validation; output_path is None. Without CSV, csv_path is None.
    include_filename: include the original basename in CSV (default True).
        False leaves that CSV field empty; rename_output controls TIFF names.
    rename_output: use an anonymous UUID filename (default True); False keeps
        the source stem with .tiff. Collisions receive _2, _3, etc.; never overwrite.
    redactions: (x, y, width, height), painted white; requires 'lossless' or 'jpeg'.
    pixels_reviewed: caller confirms no identifiers remain outside supplied masks.
    preserve_mpp: copy only finite positive numeric microns-per-pixel calibration.
    preserve_icc: copy the original RGB ICC profile including its metadata.
        Defaults to False. If copied, metadata_clean=False and the report/CSV
        explicitly require separate ICC metadata review. Pixels are not transformed.
    tile_size: controls TIFF re-encoding. workers: controls parallel TIFF encoding.
        Preserve mode retains source coding geometry (apart from NDPI regrouping).
    progress: receives {stage, completed, total, percent}; no source identifiers.
    cancelled: cooperative callback evaluated between tiles; True aborts export.

    Preserve mode removes JPEG APP/COM metadata, retains entropy-coded data and
    coding tables, and reconstructs only structural JPEG headers/restart markers
    where required. Verifies every output compressed tile by SHA-256 and decodes
    every tile. Also compares source/output pixels in 25 regions with OpenSlide.
    Source padding pixels are retained; masks require explicit lossless mode.
    Lossless mode verifies every decoded tile against the supplied RGB pixels.
    Both exclude source descriptions, associated images and unreferenced file data.
    ICC is excluded unless preserve_icc=True; this is an explicit review exception.
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
    if not all(isinstance(v, bool) for v in (export_image, export_csv, include_filename, rename_output, pyramid, preserve_icc)):
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
    if compression not in ("preserve", "lossless", "jpeg", "jpeg2000", "philips"):
        raise ValueError("compression must be preserve, lossless, jpeg, jpeg2000 or philips")
    if compression == "philips" and export_image:
        if source.suffix.lower() not in PHILIPS_EXTENSIONS:
            raise ValueError("Native Philips export requires iSyntax/i2syntax input")
        if redactions or not pyramid or not preserve_mpp:
            raise ValueError("Native Philips export preserves original pixels, levels and calibration; use TIFF for masks or altered geometry")
        return _export_philips_native(source, base, run_id, export_csv, include_filename,
            rename_output, pixels_reviewed, preserve_icc, workers, progress, cancelled)
    if compression == "preserve" and redactions:
        raise ValueError("Pixel redactions require compression=lossless; preserve mode never re-encodes")
    if source.suffix.lower() in PHILIPS_EXTENSIONS and compression == "preserve" and export_image:
        raise ValueError("Philips iSyntax/i2syntax cannot preserve JPEG coding data. Select compression='lossless' (SDK display RGB to Deflate).")
    openslide, dll = _openslide()
    temporary = None
    last_progress = [None]

    def emit(stage, completed, total):
        if cancelled is not None and cancelled():
            raise ExportCancelled("Export cancelled")
        if progress is not None:
            if pyramid and export_image:
                base, scale = {"write": (0, 55), "verify": (55, 25), "pyramid": (80, 15), "finalize": (95, 5)}[stage]
            else:
                base, scale = (0, 70) if stage == "write" else (70, 30)
            percent = round(base + scale * completed / max(1, total), 1)
            if last_progress[0] != (stage, percent):
                last_progress[0] = (stage, percent)
                progress({"stage": stage, "completed": completed, "total": total,
                          "percent": percent})

    try:
        stat_before = source.stat()
        with _open_slide(source, openslide, cancelled) as slide:
            before_inventory = _inventory(source, slide) if export_image else None
            dimensions = [slide.dimensions]
            downsamples = [1.0]
            source_level_count = slide.level_count
            source_mpp = (_numeric_property(slide, "openslide.mpp-x"),
                          _numeric_property(slide, "openslide.mpp-y"))
            objective = _objective_power(slide)
            if any(w <= 0 or h <= 0 for w, h in dimensions):
                raise ValueError("Invalid image dimensions")
            if any(not math.isfinite(d) or d < 1 for d in downsamples):
                raise ValueError("Invalid image pyramid")
            boxes = _rectangles(redactions, *dimensions[0])
            mpp = None
            if preserve_mpp and all(v is not None for v in source_mpp):
                mpp = source_mpp
            source_vendor = _source_vendor(slide)
            technical = _technical_metadata(dimensions[0], mpp, objective, source_vendor)
            source_technical = _technical_metadata(dimensions[0], source_mpp, objective, source_vendor)
            physical = {key: source_technical[key] for key in ("physical_width_mm", "physical_height_mm")}
            if isinstance(slide, PhilipsSlide):
                rendering = {"source_representation": "Philips SDK display RGB 8-bit",
                             "source_origin_x_px": slide.display_origin[0],
                             "source_origin_y_px": slide.display_origin[1]}
                technical.update(rendering)
                source_technical.update(rendering)
                physical.update(rendering)
            icc = None
            if preserve_icc and export_image:
                with slide.read_region((0, 0), 0, (1, 1)) as region:
                    icc = region.info.get("icc_profile")
                if icc:
                    from io import BytesIO
                    from PIL import ImageCms
                    if len(icc) > 64 * 1024 * 1024:
                        raise ValueError("ICC profile exceeds 64 MiB limit")
                    profile = ImageCms.ImageCmsProfile(BytesIO(icc))
                    if profile.profile.xcolor_space.strip() != "RGB":
                        raise ValueError("Only RGB ICC profiles can accompany RGB output")
            physical.update(source_vendor=source_vendor, icc_profile_copied=bool(icc), icc_review_required=bool(icc))
            description = _technical_description(technical)
            tiles_per_level = [math.ceil(w / tile_size) * math.ceil(h / tile_size)
                               for w, h in dimensions]
            total = sum(tiles_per_level)
            folder = _run_folder(base, run_id)
            output_stem = "anonymous_" + uuid.uuid4().hex if rename_output else source.stem
            target = folder / (output_stem + ".tiff")
            if not export_image:
                emit("write", 0, 1)
                row = {
                    **physical,
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
                        "compression": None, "mpp": list(source_mpp), "objective_power": objective,
                        "technical_metadata": source_technical}
            fd, name = tempfile.mkstemp(prefix=".wsi_", suffix=".partial.tiff", dir=target.parent)
            os.close(fd)
            temporary = Path(name)
            if compression == "preserve":
                verified = _preserve_jpeg(source, temporary, dimensions, mpp, emit, description=description, icc=icc)
            elif compression == "jpeg":
                verified = _write_jpeg(slide, temporary, mpp, boxes, tile_size, emit, description, icc)
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
                            compression=33005 if compression == "jpeg2000" else "deflate",
                            compressionargs={"reversible": True, "codecformat": "J2K", "mct": True} if compression == "jpeg2000" else {"level": 1},
                            metadata=None, description=description if level == 0 else None, software=False, datetime=False,
                            iccprofile=icc if level == 0 else None,
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
                        _validate_metadata(page, allowed_tags, description if level == 0 else None, icc if level == 0 else None)
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
            preserved_levels = 1 if compression == "preserve" else 0
            generated_levels = 0
            if pyramid:
                dimensions, extra_verified, preserved_levels, generated_levels = _append_pyramid(
                    source, temporary, slide, openslide, mpp, compression, emit, description, icc)
                verified += extra_verified
            with openslide.OpenSlide(str(temporary)) as check:
                if list(check.level_dimensions) != dimensions or check.associated_images:
                    raise ValueError("Output pyramid/level readback failed")
                if check.properties.get("openslide.vendor") != "aperio":
                    raise ValueError("Output is not an Aperio-compatible tiled TIFF")
                with check.read_region((0, 0), 0, (64, 64)) as region:
                    region.load()
                    if region.info.get("icc_profile") != icc:
                        raise ValueError("OpenSlide ICC readback failed")
                if _numeric_property(check, "openslide.objective-power") != objective:
                    raise ValueError("Output objective-power validation failed")
                if pyramid:
                    with check.get_thumbnail((512, 512)) as thumbnail:
                        thumbnail.load()
                        if max(thumbnail.size) > 512:
                            raise ValueError("Output thumbnail validation failed")
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
            if pyramid:
                emit("finalize", 1, 1)
            stat_after = source.stat()
            if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
                raise ValueError("Input changed during export")
            if cancelled is not None and cancelled():
                raise ExportCancelled("Export cancelled")
            # Atomic no-clobber publication on both Windows and POSIX.
            audit = _removal_audit(before_inventory, _inventory(temporary), rename_output=rename_output,
                                  include_filename=include_filename, export_csv=export_csv,
                                  icc=icc, reviewed=pixels_reviewed)
            if isinstance(slide, PhilipsSlide):
                audit["scope"] = "Philips SDK associated-image inventory; source XML excluded by policy; no patient-field detection"
                audit["entries"].append({"item": "philips_metadata", "status": "excluded_by_policy",
                    "before": "not_assessed", "after": "technical_metadata"})
            suffix = 1
            while True:
                try:
                    if os.name == "nt":
                        os.rename(temporary, target)
                    else:
                        os.link(temporary, target)
                        temporary.unlink()
                    break
                except FileExistsError:
                    if rename_output:
                        raise
                    suffix += 1
                    target = folder / f"{output_stem}_{suffix}.tiff"
            temporary = None
            result = {
                "output_path": str(target), "directory": str(folder),
                "format": "pyramidal-bigtiff" if pyramid else "single-page-bigtiff",
                "pyramid": pyramid, "preserved_levels": preserved_levels, "generated_levels": generated_levels,
                "thumbnail_verified": pyramid,
                "status": "metadata_clean_pixels_reviewed" if pixels_reviewed else "metadata_clean_pixel_review_required",
                "metadata_clean": not bool(icc), "icc_review_required": bool(icc), "pixel_review_asserted_by_caller": pixels_reviewed,
                "redaction_count": len(boxes), "level_dimensions": [list(d) for d in dimensions],
                "objective_power": objective,
                "rename_output": rename_output,
                "technical_metadata": technical,
                "anonymization_audit": audit,
                "mpp": list(mpp) if mpp else None,
                "compression": {"preserve": "jpeg-preserved", "lossless": "deflate-lossless", "jpeg": "jpeg-reencoded-q90", "jpeg2000": "jpeg2000-lossless"}[compression],
                "additional_lossy_compression": compression == "jpeg",
                "jpeg_quality": 90 if compression == "jpeg" else None,
                "all_output_tiles_verified": True, "verified_tiles": verified,
                "verification": "compressed-sha256-and-all-tiles-decode" if compression in ("preserve", "jpeg") else
                                ("base-pixels-sha256-and-pyramid-compressed-sha256" if pyramid else "all-decoded-pixels-sha256"),
                "source_output_pixel_regions_verified": 25 if compression == "preserve" else 0,
                "source_metadata_copied": False, "associated_images_copied": False,
                "source_compressed_payload_copied": compression == "preserve",
                "jpeg_app_com_removed": compression in ("preserve", "jpeg"),
                "reencoded": compression != "preserve" or generated_levels > 0,
                "base_image_reencoded": compression != "preserve", "icc_profile_copied": bool(icc),
                "icc_profile_bytes": len(icc) if icc else 0, "source_vendor": source_vendor,
                "representation": ("Philips SDK display view, 8-bit RGB; not raw internal samples" if isinstance(slide, PhilipsSlide)
                                   else "OpenSlide 2D RGB; not all focal planes/channels"),
                "size_bytes": target.stat().st_size,
            }
            if isinstance(slide, PhilipsSlide):
                result["philips_display_origin"] = slide.display_origin
            if icc:
                result["status"] = "icc_review_required_" + ("pixels_reviewed" if pixels_reviewed else "pixel_review_required")
            row = {
                **physical,
                "original_filename": source.name if include_filename else "", "output_filename": target.name,
                "source_format": source.suffix.lower(), "mpp_x_um": source_mpp[0], "mpp_y_um": source_mpp[1],
                "width_px": dimensions[0][0], "height_px": dimensions[0][1],
                "objective_power": objective, "source_level_count": source_level_count, "output_pages": len(dimensions),
                "source_size_bytes": stat_before.st_size, "output_size_bytes": result["size_bytes"],
                "compression": result["compression"], "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": result["status"], "verified_tiles": verified,
                "pixel_review_asserted_by_caller": pixels_reviewed,
                "anonymization_audit": json.dumps(audit, ensure_ascii=True, separators=(",", ":")),
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
    parser.add_argument("--compression", choices=("preserve", "lossless", "jpeg", "jpeg2000", "philips"), default="preserve")
    parser.add_argument("--single-image", action="store_true", help="Disable pyramid output")
    parser.add_argument("--keep-filename", action="store_true", help="Keep source basename with .tiff extension")
    parser.add_argument("--preserve-icc", action="store_true", help="Copy original ICC; profile metadata requires separate review")
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
                           pixels_reviewed=args.pixels_reviewed, compression=args.compression,
                           pyramid=not args.single_image, rename_output=not args.keep_filename,
                           preserve_icc=args.preserve_icc, progress=show_progress)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    _main()
