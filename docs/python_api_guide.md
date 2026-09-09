# Python 함수 사용 가이드

현재 코드와 v1.5.0 기능 기준입니다. EXE나 GUI를 실행하지 않고 `anonymize_wsi()`를 호출할 수 있습니다. 함수는 변환·검증·저장을 마친 뒤 결과 딕셔너리를 반환합니다.

## 1. 필요한 파일과 실행 환경

다른 프로젝트에서는 **`wsi_anonymizer.py` 한 파일**을 가져가면 됩니다. `app.py`, `wsi_app`, 로고, PySide6, PyInstaller는 함수 사용에 필요하지 않습니다. 의존 라이브러리는 설치해야 합니다.

```text
my_project/
├─ wsi_anonymizer.py
├─ run_export.py
└─ data/
   ├─ sample.svs
   └─ sample.ndpi
```

이 프로젝트에서 검증한 환경은 Windows x64, `yslee`의 Python 3.12입니다. PowerShell에서 실행합니다.

```powershell
conda activate yslee
python -c "import sys; print(sys.executable)"
python -c "import openslide; print(openslide.__version__, openslide.__library_version__)"
```

새 환경에서 함수 실행용 라이브러리만 설치하려면:

```powershell
python -m pip install openslide-python==1.4.6 openslide-bin==4.0.1.2 tifffile==2025.12.20 imagecodecs==2026.8.16 "numpy>=1.26" "Pillow>=10"
```

프로젝트 GUI까지 설치할 때는 저장소 루트에서 `python -m pip install -r requirements.txt`를 사용합니다. 위 설치 조합은 현재 프로젝트 기준이며 다른 OS·Python 버전까지 검증한 것은 아닙니다.

## 2. 가장 간단한 실행

아래를 `run_export.py`로 저장하고 `python run_export.py`로 실행합니다. 경로는 실행 시 작업 폴더 기준입니다. Windows 절대 경로는 `r"D:\slides\sample.svs"`처럼 작성할 수 있습니다.

```python
from wsi_anonymizer import anonymize_wsi

result = anonymize_wsi(
    input_path="data/sample.svs",   # .ndpi도 같은 함수 사용
    output_dir="output",           # TIFF 파일명이 아니라 출력 폴더
    compression="preserve",
    pyramid=True,
    rename_output=True,
    include_filename=False,       # API 기본값은 True; 이 예제는 원본 이름을 CSV에서 제외
    preserve_mpp=True,
    preserve_icc=False,
    pixels_reviewed=False,
)

print("TIFF:", result["output_path"])
print("CSV:", result["csv_path"])
print("상태:", result["status"])
print("배율:", result["objective_power"])
print("원본 벤더:", result["technical_metadata"]["source_vendor"])
```

결과 구조:

```text
output/
└─ YYYYMMDD_HHMMSS_ffffff/
   ├─ anonymous_<임의 ID>.tiff
   └─ metadata.csv
```

원본을 덮어쓰지 않습니다. 출력 확장자는 `.tiff`입니다. 날짜·시간은 실행 PC의 로컬 시각입니다. `output_dir`를 생략하면 원본 파일의 부모 폴더 아래 `output`을 사용합니다.

## 3. 인자 전체 목록

`input_path`, `output_dir` 외에는 키워드 인자로 전달합니다.

| 인자 | 기본값 | 의미 |
|---|---|---|
| `input_path` | 필수 | 원본 파일 경로. 문자열 또는 `Path` |
| `output_dir` | `None` | 결과를 둘 상위 폴더 |
| `run_id` | `None` | `YYYYMMDD_HHMMSS_ffffff` 형식. 같은 값으로 순차 호출하면 같은 폴더/CSV 사용 |
| `compression` | `"preserve"` | 원본 JPEG 보존. 또는 `"lossless"`: RGB/Deflate 재저장 |
| `pyramid` | `True` | 피라미드 TIFF. `False`면 최대 해상도 단일 영상 |
| `export_image` | `True` | TIFF 저장 여부 |
| `export_csv` | `True` | CSV 저장 여부. 이미지/CSV 중 하나 이상은 선택해야 함 |
| `include_filename` | `True` | CSV의 `original_filename`에 원본 이름 포함 |
| `rename_output` | `True` | 익명 파일명 사용. `False`면 원본 이름 + `.tiff`, 충돌 시 `_2`, `_3` 추가 |
| `redactions` | `()` | `(x, y, width, height)` 사각형 목록. 최대 해상도 픽셀 좌표, 흰색 처리 |
| `pixels_reviewed` | `False` | 사용자가 영상 개인정보를 검토했다는 확인 기록 |
| `preserve_mpp` | `True` | TIFF에 X/Y MPP 및 실제 영상 영역 크기 저장 |
| `preserve_icc` | `False` | 원본 RGB ICC 포함. 프로파일 내부 부가정보도 복사되므로 별도 검토 필요 |
| `tile_size` | `512` | Deflate 경로의 타일 크기. 128~2048, 16의 배수 |
| `workers` | `4` | Deflate 경로의 작업 수. 1~16 |
| `progress` | `None` | 진행 이벤트 딕셔너리를 받는 함수 |
| `cancelled` | `None` | 취소 요청 시 `True`를 반환하는 함수 |

`tile_size`, `workers`는 보존 모드의 원본 타일 크기를 바꾸지 않습니다. `include_filename`과 `rename_output`은 독립적입니다. `preserve_mpp=False`여도 CSV에는 읽을 수 있는 원본 MPP가 기록됩니다.

### 압축 보존의 범위

- `preserve`: 호환되는 원본 최대 해상도와 조직 축소 레벨의 JPEG 코딩 데이터를 재사용합니다. 더 작은 레벨이 필요하면 해당 레벨만 JPEG 품질 90으로 생성합니다. **모든 레벨이 원본 바이트 그대로라는 뜻은 아닙니다.**
- `lossless`: OpenSlide가 읽은 2D RGB를 Deflate로 저장합니다. 원본 JPEG 바이트 보존이 아니며 파일이 커질 수 있습니다. 모든 초점면·채널 보존 기능은 아닙니다.
- 모든 SVS·NDPI 내부 배치가 보존 모드로 지원되는 것은 아닙니다. 현재 호환 JPEG 타일/NDPI restart 구조만 지원하며, 불가능하면 오류를 반환합니다. 자동으로 다른 압축 방식으로 바꾸지 않습니다.
- 보존 모드라도 TIFF 구조·반복 헤더·축소 레벨 때문에 원본보다 커질 수 있습니다.

## 4. SVS와 NDPI 일괄 처리

하나의 실행 폴더와 CSV로 묶는 순차 처리 예제입니다. **동일 폴더/CSV에 여러 작업을 동시에 쓰는 병렬 배치는 사용하지 마세요.** CSV 잠금 충돌이 나면 해당 작업이 실패할 수 있습니다. 별도 작업을 동시에 실행해야 한다면 서로 다른 출력 폴더 또는 `run_id`를 사용합니다.

```python
from datetime import datetime
from pathlib import Path
from wsi_anonymizer import anonymize_wsi

run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
sources = sorted(
    p for p in Path("data").rglob("*")
    if p.is_file() and p.suffix.lower() in {".svs", ".ndpi"}
)

results = []
for source in sources:
    result = anonymize_wsi(
        source, "output", run_id=run_id,
        include_filename=False, preserve_icc=False,
    )
    results.append(result)
    print(result["output_path"], result["status"])
```

이 예제는 오류가 나면 그 시점에서 중단합니다. 앞에서 성공한 파일은 유지됩니다. Excel이 기존 CSV 교체를 막으면 `metadata_<시각>.csv`로 전체 목록을 저장할 수 있으므로, CSV 위치는 고정 이름 대신 **반환된 `csv_path`**를 사용하세요.

## 5. 자주 쓰는 옵션

```python
from wsi_anonymizer import anonymize_wsi

# 원본 이름 유지: sample.ndpi -> sample.tiff
named = anonymize_wsi("data/sample.ndpi", "output", rename_output=False)

# TIFF만 저장: csv_path는 None
image_only = anonymize_wsi("data/sample.svs", "output", export_csv=False)

# CSV만 저장: output_path는 None. 영상 변환·제거 검증은 수행하지 않음
csv_only = anonymize_wsi(
    "data/sample.svs", "output", export_image=False, include_filename=False,
)

# 단일 해상도 TIFF
single = anonymize_wsi("data/sample.svs", "output", pyramid=False)

# 원본 ICC 보존: ICC 내부 정보는 별도 검토 대상
with_icc = anonymize_wsi("data/sample.svs", "output", preserve_icc=True)
print(with_icc["icc_profile_copied"], with_icc["icc_review_required"])
```

위 블록은 서로 다른 작업 예시입니다. 필요한 호출만 선택하세요. ICC가 없는 원본에는 임의의 프로파일을 추가하지 않습니다. ICC가 실제 복사되면 `metadata_clean=False`, `icc_review_required=True`입니다. ICC를 넣는 옵션 자체가 픽셀 색상을 변환하지는 않습니다.

## 6. 영상의 특정 영역 가리기

마스크를 쓰려면 `compression="lossless"`가 필요합니다. 좌표는 최대 해상도 원본의 좌상단 `(0, 0)` 기준이며, 사각형은 영상 범위 안에 있어야 합니다. 실제로 확인한 식별자 위치로 바꿔 사용하세요.

```python
from wsi_anonymizer import anonymize_wsi

masked = anonymize_wsi(
    "data/sample.svs", "output",
    compression="lossless",
    redactions=[(100, 200, 300, 80)],  # x, y, 가로, 세로 (픽셀)
    include_filename=False,
    pixels_reviewed=False,
)
print(masked["redaction_count"])
```

피라미드는 마스킹된 출력에서 생성합니다. `pixels_reviewed=True`는 직접 검토한 경우에만 설정하세요. 이 인자는 자동 식별자 탐지나 추가 삭제를 실행하지 않습니다.

## 7. 진행률과 취소

함수는 **동기식**으로 실행됩니다. 웹 서버·Qt 등 다른 UI에 붙일 때는 해당 앱의 작업 스레드/프로세스에서 호출하고 진행 이벤트를 UI로 전달하세요. 콜백도 변환 작업을 실행하는 문맥에서 호출됩니다.

```python
from threading import Event
from wsi_anonymizer import anonymize_wsi, ExportCancelled

stop_event = Event()

def on_progress(event):
    print(f"{event['stage']}: {event['percent']:.1f}%")

try:
    result = anonymize_wsi(
        "data/sample.svs", "output",
        include_filename=False,
        progress=on_progress,
        cancelled=stop_event.is_set,
    )
except ExportCancelled:
    print("취소됨")
```

앱의 다른 스레드/버튼에서 `stop_event.set()`을 호출하면 다음 취소 확인 지점에서 중단합니다. 위 예제 자체에는 취소 버튼이 없습니다. 진행 이벤트는 `stage`, `completed`, `total`, `percent`이며 단계는 `write`, `verify`, `pyramid`, `finalize` 중 해당되는 것만 발생합니다. `completed/total`은 단계별 단위이고 `percent`는 전체 진행률입니다. 100% 이벤트 이후에도 최종 파일/CSV 저장이 실패할 수 있으므로, **함수가 정상 반환한 것을 성공 기준으로 사용하세요.**

취소·오류 시 해당 작업의 미완성 TIFF를 정리합니다. 빈 실행 폴더는 남을 수 있고, 프로세스를 강제 종료하면 임시 파일이 남을 수 있습니다. 이미 완료된 다른 작업 결과는 제거하지 않습니다.

## 8. 반환값 읽기

반환값은 JSON으로 저장할 수 있는 `dict`입니다. CSV 전용 결과에는 영상 검증 관련 키가 없으므로 `.get()`을 사용하거나 `format`을 먼저 확인하세요.

| 키 | 의미 |
|---|---|
| `output_path`, `directory`, `csv_path` | TIFF, 실행 폴더, 실제 CSV 경로 |
| `format` | `pyramidal-bigtiff`, `single-page-bigtiff`, `csv-only` |
| `technical_metadata` | 원본 벤더·배율·픽셀 크기·MPP·실제 영상 영역 크기 |
| `objective_power` | 배율 숫자. 없으면 `None` |
| `level_dimensions` | 레벨별 `[가로, 세로]` |
| `mpp` | 출력 X/Y MPP. MPP 보존을 해제했거나 읽을 수 없으면 `None`; CSV 전용은 원본 MPP |
| `preserved_levels`, `generated_levels` | 원본 보존 레벨 수, 생성 레벨 수 |
| `base_image_reencoded` | 최대 해상도 재인코딩 여부 |
| `reencoded` | 축소 레벨 생성까지 포함한 재인코딩 여부 |
| `all_output_tiles_verified`, `verified_tiles` | 전체 출력 타일 검증과 검증 수 |
| `icc_profile_copied`, `icc_profile_bytes` | ICC 복사 여부와 크기 |
| `metadata_clean`, `icc_review_required` | 프로그램의 메타데이터 처리 상태. 완전 익명화 인증 아님 |
| `anonymization_audit` | 실제 제거/보존 비교 내역 |
| `status` | 아래 상태 코드 |

`technical_metadata`의 키는 `schema`, `source_vendor`, `objective_power`, `width_px`, `height_px`, `mpp_x_um`, `mpp_y_um`, `physical_width_mm`, `physical_height_mm`입니다. 실제 크기는 픽셀 수 × MPP / 1000(mm)이며 여백을 포함한 전체 영상 영역입니다. 알 수 없는 배율·MPP는 추정하지 않습니다.

| `status` | 의미 |
|---|---|
| `metadata_clean_pixel_review_required` | 메타데이터 처리 완료, 영상 검토 필요 |
| `metadata_clean_pixels_reviewed` | 메타데이터 처리 완료, 사용자 영상 검토 확인 |
| `icc_review_required_pixel_review_required` | ICC와 영상 모두 별도 검토 필요 |
| `icc_review_required_pixels_reviewed` | 사용자 영상 검토 확인, ICC는 별도 검토 필요 |
| `technical_metadata_only` | CSV 전용, 영상 변환·검증 미수행 |

`metadata_clean=True`여도 영상 속 식별자, 원본 이름을 유지한 출력 파일명, 원본 이름을 포함한 CSV까지 익명이라고 보장하지 않습니다.

## 9. 제거 내역 확인

```python
# 앞서 정상 반환된 result 사용
audit = result.get("anonymization_audit")
if audit:
    for entry in audit["entries"]:
        print(entry["item"], entry["status"])
    print("출력에 없는 원본 TIFF 태그:", audit["removed_tag_codes"])
else:
    print("제거 검증 내역 없음: CSV 전용인지 확인하세요.")
```

주요 항목은 `description`, `software`, `datetime`, `document_name`, `artist`, `host`, `icc`, `label`, `macro`, `thumbnail`, `other`, `filename`, `csv_filename`, `pixels`, `icc_review`, `jpeg_app_com`입니다.

| 내역 상태 | 의미 |
|---|---|
| `removed` | 존재했던 항목의 제거 확인 |
| `rewritten` | 원본 내용을 제외하고 새로운 기술 정보로 작성 |
| `retained` | 보존 |
| `not_present` | 비교 대상 TIFF 태그/OpenSlide 항목이 원본에 없음 |
| `not_checked` | 해당 비교 불가 |
| `renamed` / `excluded` | 익명 파일명으로 변경 / CSV 원본 이름 제외 |
| `not_exported` | CSV를 저장하지 않음 |
| `review_required` / `user_reviewed` | 별도 검토 필요 / 사용자 검토 확인 |
| `not_applicable` | 해당 없음 |
| `excluded_by_policy` | 출력 제외 정책 적용. 원본 존재 여부 미집계 |

비교 범위는 최상위 TIFF 태그와 OpenSlide 부속 이미지입니다. `datetime=not_present`는 TIFF DateTime 태그가 없다는 뜻이며 설명문 안에도 날짜가 없다는 뜻은 아닙니다. JPEG APP/COM은 `excluded_by_policy`로 기록합니다. 개인정보 원문을 내역에 다시 넣지 않습니다.

CSV에서는 `anonymization_audit` 열을 `json.loads()`로 읽으면 같은 내역을 얻습니다. CSV 전용 작업의 이 열은 빈 문자열이므로 파싱 전에 확인하세요.

## 10. OpenSlide에서 결과 읽기

```python
import json
import openslide

with openslide.OpenSlide(result["output_path"]) as slide:
    print("배율:", slide.properties.get("openslide.objective-power"))  # 예: '40'
    print("출력 호환 벤더:", slide.properties["openslide.vendor"])    # aperio
    print("레벨:", slide.level_dimensions)

    description = slide.properties["tiff.ImageDescription"]
    technical = json.loads(description.split("|WSI_Technical=", 1)[1])
    print("원본 벤더:", technical["source_vendor"])
    print("정확한 X/Y MPP:", technical["mpp_x_um"], technical["mpp_y_um"])

    with slide.get_thumbnail((512, 512)) as thumbnail:
        thumbnail.save("preview.png", icc_profile=thumbnail.info.get("icc_profile"))

    print("ICC 존재:", slide.color_profile is not None)
```

이 읽기 예제는 현재 프로그램으로 생성한 TIFF용입니다. 원본 SVS·NDPI의 설명문은 위 JSON 구조가 아닐 수 있습니다.

- 출력은 Aperio 호환 TIFF라서 `openslide.vendor`가 `aperio`입니다. 원본 스캐너가 Aperio라는 뜻은 아닙니다. 원본 벤더는 `technical_metadata.source_vendor`를 사용합니다.
- OpenSlide 속성 값은 문자열입니다. 배율이 있으면 `float(value)`로 변환할 수 있습니다. 원본에 배율이 없으면 배율 키를 만들지 않습니다.
- X/Y MPP가 같은 경우에는 `openslide.mpp-x/y`로도 읽힙니다. X/Y가 다르면 해당 두 키를 생략하고 정확한 두 값을 기술 JSON·표준 TIFF 해상도 태그·CSV에 유지합니다.
- 큰 단일 해상도 TIFF에서 `get_thumbnail()`은 최대 해상도를 읽을 수 있습니다. 일반적인 미리보기에는 기본 피라미드 출력을 사용하세요.
- `color_profile`의 존재와 자동 색상 보정은 별개입니다. 표시 앱이 ICC 색상 관리를 적용해야 합니다.

## 11. 오류 처리와 통합 시 유의점

```python
import openslide
from wsi_anonymizer import anonymize_wsi, ExportCancelled

try:
    result = anonymize_wsi("data/sample.ndpi", "output", include_filename=False)
except ExportCancelled:
    print("사용자 취소")
except (ValueError, TypeError):
    print("인자 또는 입력 영상의 내부 구조를 확인하세요.")
except openslide.OpenSlideError:
    print("OpenSlide에서 영상을 읽지 못했습니다.")
except OSError:
    print("파일 경로, 권한, 잠금, 저장 공간을 확인하세요.")
```

- `ModuleNotFoundError`/DLL 오류: 실행 중인 Python이 `yslee`인지, 필요한 패키지가 같은 환경에 설치됐는지 확인합니다. 의존성 로드는 함수 호출 전에 실패할 수도 있습니다.
- `Compression preservation...`, `Unsupported NDPI...` 등: 해당 입력의 보존 모드 미지원입니다. 재저장과 용량 증가를 허용할 때만 명시적으로 `compression="lossless"`를 선택합니다.
- 마스크 오류: 보존 모드인지, 사각형 크기와 좌표가 최대 해상도 영상 범위 안인지 확인합니다.
- 저장 공간: 대용량 TIFF와 임시 파일을 둘 여유가 필요합니다. Deflate는 크게 증가할 수 있습니다.
- CSV 잠금/Excel: 반환 `csv_path`를 사용합니다. CSV 저장까지 실패하면 해당 호출에서 새로 만든 TIFF도 정리합니다.
- 변환 중에는 원본이나 원본에 필요한 사이드카 파일을 수정하지 않습니다.
- 긴 변환은 HTTP 요청 처리나 GUI 메인 스레드에서 직접 실행하지 말고 작업 관리 계층에서 호출하세요. 콜백에서 무거운 처리나 직접적인 다른 스레드 UI 조작을 하지 마세요.

## 12. 공유 전 확인

공유용 예제에서는 `rename_output=True`, `include_filename=False`, `preserve_icc=False`를 사용했습니다. 이는 함수 기본값 전체와 같지 않습니다. 실제 업무 목적에 맞게 명시적으로 지정하세요.

이 프로그램은 조직 영상 속 글자를 자동으로 탐지·제거하지 않습니다. 영상 자체를 검토하고 필요한 영역을 마스킹해야 합니다. `pixels_reviewed`, `metadata_clean`, 제거 내역 어느 하나도 완전한 익명화의 자동 인증으로 사용하지 마세요.

관련 문서: [전체 사용 안내](../README.md), [처리 정책](processing_policy.md), [검증 기록](release_validation.md).
