from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

from tools.inspect_samples import inspect, load_openslide, safe_thumbnail
from wsi_app.engine import create_anonymized_tiff
from wsi_anonymizer import ExportCancelled


def emit(kind, **payload):
    print(json.dumps({"kind": kind, **payload}, ensure_ascii=True), flush=True)


def main():
    dll = None
    try:
        job = json.loads(sys.stdin.readline())
        openslide, dll = load_openslide()
        path = Path(job["source"])
        if job["action"] == "copy":
            def progress(event):
                stage = "TIFF 저장" if event["stage"] == "write" else "전체 타일 검증"
                emit("progress", message=f"{stage} · {event['percent']}%", percent=event["percent"])
            result = create_anonymized_tiff(
                path, Path(job["output"]), run_id=job.get("run_id"), pixels_reviewed=job.get("pixels_reviewed", False),
                progress=progress, cancelled=lambda: Path(job["cancel_file"]).exists(),
                **{key: job[key] for key in ("export_image", "export_csv", "include_filename", "preserve_mpp", "compression") if key in job})
            emit("result", action="copy", data=result)
        else:
            emit("progress", message="구조 검사 및 영상 읽기")
            result = inspect(path, "preview", openslide)
            preview = None
            if not result["errors"]:
                with openslide.OpenSlide(str(path)) as slide:
                    thumbnail = safe_thumbnail(slide, (700, 480))
                    if thumbnail is not None:
                        buffer = io.BytesIO()
                        thumbnail.save(buffer, format="PNG")
                        preview = base64.b64encode(buffer.getvalue()).decode("ascii")
                        thumbnail.close()
            emit("result", action="inspect", data=result, preview=preview)
        return 0
    except ExportCancelled:
        emit("cancelled", message="TIFF 내보내기를 중지했습니다. 미완성 파일은 정리했습니다.")
        return 0
    except (ValueError, OSError) as exc:
        # Known engine messages contain no raw metadata. OS errors may contain paths.
        message = str(exc) if isinstance(exc, ValueError) else "파일 접근 또는 저장에 실패했습니다. 경로와 여유 공간을 확인하세요."
        emit("error", message=message, error_type=type(exc).__name__)
        return 1
    except Exception as exc:
        emit("error", message="처리에 실패했습니다. 지원 형식과 환경을 확인하세요.", error_type=type(exc).__name__)
        return 1
    finally:
        if dll is not None:
            dll.close()
