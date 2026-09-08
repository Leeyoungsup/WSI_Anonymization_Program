from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

from tools.inspect_samples import inspect, load_openslide
from wsi_app.engine import create_review_copy, UnsupportedFormat


def emit(kind, **payload):
    print(json.dumps({"kind": kind, **payload}, ensure_ascii=True), flush=True)


def main():
    dll = None
    try:
        job = json.loads(sys.stdin.readline())
        openslide, dll = load_openslide()
        path = Path(job["source"])
        if job["action"] == "copy":
            result = create_review_copy(path, Path(job["output"]), openslide,
                                        lambda message: emit("progress", message=message))
            emit("result", action="copy", data=result)
        else:
            emit("progress", message="구조 검사 및 영상 읽기")
            result = inspect(path, "preview", openslide)
            preview = None
            if not result["errors"]:
                with openslide.OpenSlide(str(path)) as slide:
                    with slide.get_thumbnail((700, 480)) as thumbnail:
                        buffer = io.BytesIO()
                        thumbnail.save(buffer, format="PNG")
                        preview = base64.b64encode(buffer.getvalue()).decode("ascii")
            emit("result", action="inspect", data=result, preview=preview)
        return 0
    except (UnsupportedFormat, ValueError, OSError) as exc:
        # Known engine messages contain no raw metadata. OS errors may contain paths.
        message = str(exc) if isinstance(exc, (UnsupportedFormat, ValueError)) else "파일 접근 또는 저장에 실패했습니다. 경로와 여유 공간을 확인하세요."
        emit("error", message=message, error_type=type(exc).__name__)
        return 1
    except Exception as exc:
        emit("error", message="처리에 실패했습니다. 지원 형식과 환경을 확인하세요.", error_type=type(exc).__name__)
        return 1
    finally:
        if dll is not None:
            dll.close()
