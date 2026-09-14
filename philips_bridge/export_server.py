"""Private stdin/stdout bridge for the anonymizer, Python 3.7 / SDK 2.0.

No sockets and no file metadata logs. Pixel buffers use named Windows memory.
"""
import base64
import json
import mmap
import sys

from sdk_bootstrap import prime_sdk_dll_paths
prime_sdk_dll_paths()
from sdk_slide import SDKSlide


def main():
    slide = None
    for line in sys.stdin:
        try:
            req = json.loads(line)
            command = req["command"]
            if command == "open":
                if slide is not None:
                    slide.close()
                slide = SDKSlide(req["path"])
                data = {"dimensions": slide.dimensions, "level_dimensions": slide.level_dimensions,
                        "level_downsamples": slide.level_downsamples, "properties": slide.properties,
                        "associated_images": list(slide.associated_images),
                        "icc": base64.b64encode(slide.icc).decode("ascii") if slide.icc else None,
                        "display_origin": slide.origins[0]}
            elif command == "region":
                with slide.read_region(req["location"], req["level"], req["size"]) as image:
                    raw = image.tobytes()
                with mmap.mmap(-1, len(raw), tagname=req["memory"], access=mmap.ACCESS_WRITE) as memory:
                    memory.write(raw)
                data = {"bytes": len(raw)}
            elif command == "export_native":
                from native_export import export_native
                def progress(stage, completed, total):
                    print(json.dumps({"event": "native_progress", "stage": stage,
                                      "completed": completed, "total": total}), flush=True)
                data = export_native(slide, req["path"], req["preserve_icc"], req["workers"], progress)
            elif command == "close":
                if slide is not None:
                    slide.close()
                    slide = None
                print(json.dumps({"ok": True}), flush=True)
                break
            else:
                raise ValueError("Unknown command")
            print(json.dumps({"ok": True, "data": data}, ensure_ascii=True), flush=True)
        except Exception as exc:
            # Never relay native error messages containing paths / identifiers.
            print(json.dumps({"ok": False, "error_type": type(exc).__name__}), flush=True)
    if slide is not None:
        slide.close()


if __name__ == "__main__":
    main()
