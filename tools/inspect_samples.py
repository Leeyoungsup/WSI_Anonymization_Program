"""Read-only WSI inventory. Never export metadata values or source filenames."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import _objective_power, _numeric_property, _technical_metadata, _source_vendor, _open_slide, PHILIPS_EXTENSIONS


def load_openslide():
    # openslide-python 1.3.x needs an explicit DLL path on Windows.
    dll_handle = None
    if os.name == "nt":
        spec = importlib.util.find_spec("openslide_bin")
        if spec and spec.origin:
            dll_handle = os.add_dll_directory(str(Path(spec.origin).parent))
    import openslide
    return openslide, dll_handle


def safe_thumbnail(slide, size):
    """Avoid allocating the entire level-0 image for huge single-page TIFFs."""
    scale = max(slide.dimensions[0] / size[0], slide.dimensions[1] / size[1])
    level = slide.get_best_level_for_downsample(scale)
    width, height = slide.level_dimensions[level]
    if width * height > 40_000_000:
        return None
    return slide.get_thumbnail(size)


def inspect(path: Path, sample_id: str, openslide) -> dict:
    result = {
        "sample_id": sample_id,
        "extension": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "scope": "Structure inventory and sparse decode checks; not anonymization certification",
        "errors": [],
    }
    try:
        with tifffile.TiffFile(path) as tif:
            result["tiff"] = {
                "is_bigtiff": tif.is_bigtiff,
                "is_ndpi": tif.is_ndpi,
                "pages": [],
            }
            for index, page in enumerate(tif.pages):
                result["tiff"]["pages"].append({
                    "index": index,
                    "width": page.imagewidth,
                    "height": page.imagelength,
                    "compression": int(page.compression),
                    "is_tiled": page.is_tiled,
                    "subfiletype": int(page.subfiletype),
                    "has_subifds": bool(page.subifds),
                    "ndpi_source_lens": (
                        page.tags[65421].value
                        if tif.is_ndpi and 65421 in page.tags else None
                    ),
                    "tags": [
                        {"code": tag.code, "name": tag.name,
                         "dtype": int(tag.dtype), "count": tag.count}
                        for tag in page.tags.values()
                    ],
                })
    except Exception as exc:
        if path.suffix.lower() not in PHILIPS_EXTENSIONS:
            result["errors"].append({"stage": "tiff_inventory", "type": type(exc).__name__})
    try:
        with _open_slide(path, openslide) as slide:
            technical = _technical_metadata(slide.dimensions,
                (_numeric_property(slide, "openslide.mpp-x"), _numeric_property(slide, "openslide.mpp-y")),
                _objective_power(slide), _source_vendor(slide))
            result["openslide"] = {
                "technical_metadata": technical,
                "vendor": slide.properties.get("openslide.vendor"),
                "dimensions": slide.dimensions,
                "objective_power": _objective_power(slide),
                "mpp": [_numeric_property(slide, "openslide.mpp-x"),
                        _numeric_property(slide, "openslide.mpp-y")],
                "level_dimensions": slide.level_dimensions,
                "level_downsamples": slide.level_downsamples,
                "property_keys": sorted(slide.properties.keys()),
                "associated_images": {},
                "decoded_regions": [],
            }
            for name in slide.associated_images:
                associated = slide.associated_images[name]
                result["openslide"]["associated_images"][name] = associated.size if associated is not None else None
                if associated is not None:
                    associated.close()
            if path.suffix.lower() in PHILIPS_EXTENSIONS:
                result["openslide"]["reader"] = "Philips SDK display RGB"
                result["openslide"]["display_origin"] = slide.display_origin
            for level, (width, height) in enumerate(slide.level_dimensions):
                scale = slide.level_downsamples[level]
                size = (min(128, width), min(128, height))
                for fraction in (0.0, 0.5, 1.0):
                    location = (
                        int(max(0, width - size[0]) * fraction * scale),
                        int(max(0, height - size[1]) * fraction * scale),
                    )
                    region = slide.read_region(location, level, size)
                    region.load()
                    region.close()
                    result["openslide"]["decoded_regions"].append({
                        "level": level, "location": location, "size": size,
                    })
            thumbnail = safe_thumbnail(slide, (256, 256))
            if thumbnail is None:
                result["openslide"]["thumbnail_decode_ok"] = None
                result["openslide"]["thumbnail_skip_reason"] = "Lowest available level exceeds preview memory budget"
            else:
                thumbnail.load()
                thumbnail.close()
                result["openslide"]["thumbnail_decode_ok"] = True
    except Exception as exc:
        result["errors"].append({"stage": "openslide_decode", "type": type(exc).__name__})
        if path.suffix.lower() in PHILIPS_EXTENSIONS:
            result["errors"][-1]["message"] = "Philips SDK 2.0 could not decode this file; check file integrity and SDK compatibility."
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/sample_inventory.json"))
    args = parser.parse_args()
    paths = sorted(p for p in args.input.rglob("*")
                   if p.is_file() and p.suffix.lower() in {".svs", ".ndpi"})
    if not paths:
        parser.error("No SVS or NDPI samples found")
    if args.output.resolve().is_relative_to(args.input.resolve()):
        parser.error("Output must be outside the sample directory")
    if args.output.suffix.lower() != ".json":
        parser.error("Output must be a .json report")
    openslide, dll_handle = load_openslide()
    try:
        results = []
        for index, path in enumerate(paths, 1):
            item = inspect(path, f"sample_{index:03d}", openslide)
            results.append(item)
            summary = item.get("openslide", {})
            print(json.dumps({
                "sample_id": item["sample_id"], "extension": item["extension"],
                "size_bytes": item["size_bytes"], "dimensions": summary.get("dimensions"),
                "levels": len(summary.get("level_dimensions", [])),
                "associated_images": summary.get("associated_images"),
                "decoded_regions": len(summary.get("decoded_regions", [])),
                "errors": item["errors"],
            }), flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 1 if any(item["errors"] for item in results) else 0
    finally:
        if dll_handle is not None:
            dll_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
