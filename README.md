# WSI Anonymization Program

EXE 없이 함수로 사용하려면 [Python API 사용 가이드](docs/python_api_guide.md)를 참고하세요. 설치, 단일·일괄 실행, 전체 옵션, 반환값, OpenSlide 읽기와 제거 내역 확인 예제를 제공합니다.

SVS·NDPI를 **표준 피라미드 TIFF**로 내보냅니다. 최대 해상도와 호환되는 원본 조직 축소 레벨은 JPEG 압축 데이터를 유지합니다. 더 작은 미리보기 레벨만 생성하며 OpenSlide의 `get_thumbnail()`을 사용할 수 있습니다.

## Windows EXE

1.6.0: 익명화 내역을 **항목 / 원본 / 익명화 결과** 표로 표시합니다. 설명문·소프트웨어·날짜 등 원본 TIFF 문자열 값은 처리 직전에 GUI 메모리로 읽고, 선택한 행의 상세 내용을 아래에 표시합니다. 파일명 변경도 실제 이름으로 비교합니다. 원본 텍스트 값은 작업 프로세스·반환 JSON·CSV·출력 TIFF의 감사 내역에 넣지 않습니다. 기존 CSV 원본 파일명 옵션 및 원본 ICC 복사 옵션은 별도로 적용됩니다.

화면용 읽기는 최대 64개 IFD, 태그당 4 KiB까지이며 이후 내용은 생략 표시합니다. ICC는 바이트 크기만 표시하고 바이너리를 표시하지 않습니다. TIFF로 읽을 수 없는 입력은 원본 값 대신 비교 상태를 표시합니다. 메모리에 둔 원본 값은 목록 비우기·새 작업·창 닫기 시 지웁니다. 이전 실행에서 저장한 CSV에 원본 텍스트는 없으므로 이 화면용 원본 값을 복원할 수 없습니다.

1.5.0: 내보내기 완료 후 **익명화 내역** 탭에서 파일별 실제 처리 결과를 확인합니다. 설명문·소프트웨어·저장 일시·문서 이름·작성자·호스트·ICC와 OpenSlide 부속 이미지의 존재 여부를 확인하고, 출력 TIFF 태그와 비교합니다. 제거 확인/보존/원본에 없음/비교 불가/별도 검토 필요를 구분합니다. 원본 설명문은 새로운 기술 정보로 작성했다고 표시합니다. 파일명·CSV 파일명 선택과 영상·ICC 검토 상태도 표시합니다.

내역에는 개인정보 값이나 임의의 원본 필드 이름을 복사하지 않습니다. 원본 TIFF에서 출력에 없는 태그 번호와 상태만 API의 `anonymization_audit`, CSV의 같은 이름 열에 JSON으로 보존합니다. CSV 전용 작업은 영상 제거 검증을 하지 않으므로 이 열이 비어 있습니다. JPEG APP/COM은 제외 정책 적용으로 표시하며 원본 존재 여부나 개수를 측정했다고 주장하지 않습니다. 비교 범위는 최상위 TIFF IFD와 OpenSlide 부속 이미지이며 환자정보 필드 탐지·영상 OCR 결과가 아닙니다.

1.4.0: 제공된 MeDIAuto 로고와 아이콘을 창·EXE에 적용했습니다. 왼쪽 파일 목록, 오른쪽 내보내기 설정/슬라이드 정보 탭, 아래 출력 경로와 실행 버튼으로 화면을 정리했습니다. 작은 창에서는 설정만 스크롤할 수 있습니다. 로고 파일은 EXE에 포함되며 별도 logo 폴더 없이 실행됩니다.

1.3.0: 원본 Vendor를 TIFF 기술 JSON·CSV·정보 화면에 표시합니다. OpenSlide가 확인한 형식 벤더의 허용 목록만 사용하며 제조사 자유 텍스트·장비 일련번호는 복사하지 않습니다. NDPI의 원본 Vendor는 hamamatsu이고 출력의 `openslide.vendor`는 호환 형식인 aperio입니다. 이 버전으로 만든 결과를 재변환해도 원본 Vendor를 유지합니다. 이전 출력에 원본 Vendor 정보가 없으면 원래 제조사를 복원할 수 없습니다.

**원본 ICC 포함** 체크박스는 기본 해제입니다. 체크하면 원본 RGB ICC를 기본 TIFF 페이지에 그대로 복사하며 픽셀 색상 변환·재압축은 하지 않습니다. OpenSlide의 `slide.color_profile` 또는 `read_region(...).info['icc_profile']`로 읽을 수 있습니다. ICC가 없는 원본에는 새 프로파일을 만들지 않습니다. API는 `preserve_icc=True`, CLI는 `--preserve-icc`입니다.

ICC에는 색상 정보 외의 설명·제조사 등 부가정보가 있을 수 있습니다. 그대로 복사하므로 포함한 결과는 `icc_review_required=True`, `metadata_clean=False` 및 ICC 검토 필요 상태로 기록합니다. ICC 내용을 자동 익명화했다고 주장하지 않습니다. 기존 TIFF 개인정보 태그·라벨·매크로 제거는 유지합니다. CSV에 `source_vendor`, `icc_profile_copied`, `icc_review_required`가 추가됩니다.

`release/WSI_Anonymization-1.6.0-Windows-x64.zip`의 압축을 풀고 **WSI_Anonymization.exe**를 실행합니다. Python/Conda 설치 없이 사용할 수 있는 휴대용 EXE입니다. 샘플 원본은 배포본에 포함하지 않습니다. 코드서명은 미적용입니다.

**출력 파일명을 익명 이름으로 변경**은 기본 체크입니다. 해제하면 원본 이름에 `.tiff` 확장자를 붙이며 중복 이름은 `_2`, `_3` 등을 붙입니다. 기존 파일은 덮어쓰지 않습니다. 원본 파일명에 식별자가 있으면 결과 파일명에도 남습니다. CSV의 원본 파일명 포함 옵션과는 독립적입니다. API에서는 `rename_output=False`, CLI에서는 `--keep-filename`을 사용합니다.

1.2.0부터 Aperio 호환 설명을 사용하는 타일 TIFF로 저장합니다. OpenSlide vendor는 `aperio`이며 이는 출력 호환 형식으로서 원본 스캐너 제조사를 뜻하지 않습니다. 원본 배율이 있으면 아래 키로 직접 읽힙니다. 이전 출력은 재변환해야 합니다.

```python
import openslide
with openslide.OpenSlide('output.tiff') as slide:
    magnification = slide.properties.get('openslide.objective-power')  # 예: '40'
```

TIFF와 CSV에는 Magnification(원본 대물렌즈 배율), Pixel Size(전체 영상 가로·세로 픽셀 수), MPP(X/Y, µm/pixel), Physical Size(전체 영상 영역 가로·세로, mm)를 저장합니다. Physical Size는 픽셀 수 × MPP / 1000으로 계산하며 조직만의 크기가 아닙니다. 배율이나 MPP가 없으면 추정하지 않습니다.

TIFF 기본 페이지의 ImageDescription에는 고정된 호환 형식 표기, 숫자 AppMag, 해당되는 경우 MPP, 그리고 WSI_Technical의 `wsi-technical-v1` JSON만 새로 작성합니다. 원본 설명문은 복사하지 않습니다. API 결과의 `technical_metadata`에서 네 항목을 확인할 수 있습니다.

MPP는 표준 XResolution/YResolution 태그 및 기술 JSON·CSV에 정확한 X/Y 값을 유지합니다. Aperio OpenSlide 백엔드는 단일 MPP를 두 축에 사용하므로 X/Y가 같은 경우에만 `openslide.mpp-x`와 `openslide.mpp-y`를 제공합니다. 서로 다른 경우(현재 NDPI 샘플 포함)는 잘못된 값이 나오지 않도록 두 OpenSlide 키를 생략하며, 이 프로그램은 기술 JSON에서 정확한 두 값을 읽습니다. MPP 보존을 해제하면 TIFF의 MPP와 Physical Size도 생략합니다. 배율이 없는 원본은 배율 키를 만들지 않습니다.

파일 추가 또는 드래그 → 옵션 선택 → 출력 폴더 선택 → **선택 항목 내보내기** 순서입니다. 각 항목 옆 **i** 버튼에서 설명을 확인할 수 있습니다.

- TIFF 영상 / 슬라이드 정보 CSV: 하나 이상을 선택해야 합니다.
- CSV에 원본 파일명 포함: 해제하면 해당 열은 빈칸입니다.
- TIFF에 MPP 보존: 실제 픽셀 크기를 TIFF 해상도에 기록합니다. 해제해도 선택한 CSV에는 MPP가 남습니다.
- 압축: 원본 JPEG 유지가 기본값입니다. 무손실 Deflate를 선택하면 파일 크기가 크게 늘 수 있습니다.
- 출력 구조: 표준 피라미드 TIFF가 기본값입니다. 이전 단일 해상도 TIFF도 선택할 수 있습니다.

기본 결과 폴더는 Windows 문서 폴더의 `WSI Exports`입니다. 선택한 폴더 아래 로컬 시각 `YYYYMMDD_HHMMSS_ffffff` 폴더를 만들고 TIFF·CSV를 저장합니다. 한 GUI 일괄 실행은 같은 폴더/CSV를 공유합니다.

## 독립 함수

**wsi_anonymizer.py** 하나를 다른 프로젝트로 복사할 수 있습니다. Python 3.10 이상과 다음 의존성이 필요합니다.

```shell
pip install openslide-python "openslide-bin>=4.0.1.2" numpy tifffile imagecodecs Pillow
```

```python
from wsi_anonymizer import anonymize_wsi

result = anonymize_wsi(
    "slide.ndpi", "output",
    compression="preserve", pyramid=True,
    export_image=True, export_csv=True,
    include_filename=True, preserve_mpp=True,
)
print(result["output_path"])
print(result["csv_path"])
```

두 번째 인자는 TIFF 파일명이 아닌 출력 기본 폴더입니다. 여러 파일을 같은 폴더에 저장하려면 `datetime.now().strftime("%Y%m%d_%H%M%S_%f")`로 만든 하나의 `run_id`를 순차 호출에 전달합니다. 같은 폴더에 동시 쓰기는 지원하지 않습니다.

CSV만 선택하면 영상 변환·픽셀 검증 없이 기술 정보를 저장하며 `output_path=None`입니다. TIFF만 선택하면 `csv_path=None`입니다.

`pyramid=False`로 최대 해상도만 저장할 수 있습니다. 픽셀 마스킹은 `compression="lossless", redactions=[(x, y, 폭, 높이)]`로 요청합니다. 이 경우 축소 레벨도 마스킹된 출력에서 생성합니다.

CLI:

```shell
python wsi_anonymizer.py input.ndpi output
python wsi_anonymizer.py input.ndpi output --single-image
```

## 압축과 피라미드

원본 압축 유지 경로는 독립 baseline YCbCr JPEG 타일의 SVS/TIFF와 지원되는 NDPI restart 구조를 처리합니다. 최대 해상도의 지원하지 않는 구조는 오류로 알리며 자동 재압축하지 않습니다. NDPI는 현재 1×1 색상 샘플링과 완전한 restart 행, 호환되는 영상 크기를 요구합니다.

호환되는 원본 조직 축소 레벨도 압축을 유지합니다. 마지막 레벨의 긴 변이 512 이하가 될 때까지 검증된 출력 영상을 작은 영역씩 읽어 4배 축소 레벨을 추가합니다. 추가 레벨은 JPEG 품질 90, 명시적 lossless 모드에서는 Deflate를 사용합니다. NDPI 타일 헤더와 추가 레벨 때문에 결과가 항상 원본보다 작지는 않습니다.

반환값 `base_image_reencoded`는 최대 해상도 재압축 여부, `preserved_levels`는 압축을 유지한 레벨 수, `generated_levels`는 추가 생성 레벨 수입니다. `reencoded`는 추가 레벨을 생성해도 True입니다. 모든 채널·초점면을 보존하는 변환은 아닙니다.

## 익명화와 CSV

모든 출력 레벨에서 원본 개인정보 태그·설명·JPEG APP/COM 부가정보를 제외합니다. ICC는 기본 제외이며 명시적으로 포함하면 프로파일 내부 정보의 별도 검토가 필요합니다. 원본 라벨·매크로·별도 썸네일·미참조 파일 영역은 복사하지 않습니다. 조직 영상에 직접 적힌 식별자는 별도 검토 대상입니다. `pixels_reviewed=True`는 호출자의 검토 확인이며 자동 인증이 아닙니다. ICC 제외로 색상 관리 뷰어의 표시가 달라질 수 있습니다.

CSV는 UTF-8 BOM으로 저장하며 다음 기술 정보를 기록합니다.

| 내용 | 열 |
|---|---|
| 원본/출력 파일명 | original_filename, output_filename |
| 형식·MPP | source_format, mpp_x_um, mpp_y_um |
| 영상 크기·배율 | width_px, height_px, objective_power |
| 실제 영상 영역 크기(mm) | physical_width_mm, physical_height_mm |
| 원본/출력 레벨 수 | source_level_count, output_pages |
| 파일 크기·압축 | source_size_bytes, output_size_bytes, compression |
| 처리 시각·상태·검증 | exported_at, status, verified_tiles, pixel_review_asserted_by_caller |

환자명·환자/검체 ID·스캔 날짜·스캐너 일련번호·자유 텍스트를 메타데이터에서 CSV로 옮기지 않습니다. **원본 파일명 포함을 선택하면 파일명 자체의 개인정보는 CSV에 남습니다.** 수식으로 해석될 수 있는 파일명에는 작은따옴표를 붙입니다. 알 수 없는 기술 수치는 빈칸입니다.

검증에 성공한 결과만 CSV에 기록합니다. Excel이 `metadata.csv` 교체를 막으면 전체 목록을 담은 `metadata_<시각>.csv`로 저장하고 실제 경로를 반환합니다. 이후 호출은 최신 전체 목록을 이어서 기록합니다. CSV 저장까지 실패하면 해당 호출이 새로 만든 TIFF를 정리합니다. 원본을 변경하거나 기존 결과를 덮어쓰지 않습니다.

## OpenSlide 읽기

```python
import openslide

with openslide.OpenSlide(r"결과파일.tiff") as slide:
    preview = slide.get_thumbnail((512, 512))
    patch = slide.read_region((0, 0), 0, (512, 512))
    preview.close()
    patch.close()
```

피라미드 출력의 미리보기는 축소 레벨을 사용합니다. 단일 해상도를 선택한 대용량 파일은 get_thumbnail이 많은 메모리를 사용할 수 있어 프로그램 미리보기를 생략합니다. `yslee`는 OpenSlide Python 1.4.6 / 라이브러리 4.0.1로 직접 import와 영역 읽기를 확인했습니다. 환경 업데이트 후 기존 Python/Jupyter 커널은 재시작하세요.

진단: `python tools/check_openslide.py "결과파일.tiff"`.

## 개발·빌드·검증

소스 GUI 실행은 `Launch_WSI.vbs` 또는 `conda run --no-capture-output -n yslee python app.py`입니다.

```shell
python -m pip install -r requirements-build.txt
python tools/build_release.py
python tests/test_standalone.py
python tests/test_preserved.py
python tests/test_pyramid.py
python tests/test_export_options.py
python tests/test_release.py
python tests/test_release_gui.py
python tests/integration_tiff.py
```

마지막 명령은 실제 샘플 전체를 처리합니다. 최신 결과는 [피라미드 검증 기록](docs/pyramid_tiff_validation.md), [릴리즈 기록](docs/release_validation.md), 세부 익명화 규칙은 [처리 정책](docs/processing_policy.md)에 있습니다. 이전 단일 TIFF·Deflate·clean_tiff 결과는 과거 버전 기록입니다.
