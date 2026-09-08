"""Read-only OpenSlide diagnostic. Does not load a whole WSI into memory."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    print("Python:", sys.executable)
    try:
        import openslide  # Deliberately no application-specific DLL setup.
    except (ImportError, OSError) as error:
        print("OpenSlide import failed:", str(error))
        return 1
    print("OpenSlide Python:", openslide.__version__, "Library:", openslide.__library_version__)
    failed = False
    for filename in args.files:
        path = Path(filename).expanduser().resolve()
        try:
            with openslide.OpenSlide(str(path)) as slide:
                width, height = slide.dimensions
                for x, y in ((0, 0), (width // 2, height // 2),
                             (max(0, width - 256), max(0, height - 256))):
                    with slide.read_region((x, y), 0, (256, 256)) as patch:
                        patch.load()
                print(json.dumps({"file": str(path), "dimensions": slide.dimensions,
                                  "levels": slide.level_count, "regions_read": 3, "status": "OK"}, ensure_ascii=True))
        except Exception as error:
            failed = True
            print(json.dumps({"file": str(path), "error": type(error).__name__, "message": str(error)}, ensure_ascii=True))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
