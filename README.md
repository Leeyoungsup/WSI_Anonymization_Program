# WSI Anonymization Program

WSI의 **최대 해상도 영상 한 장만** 무손실 TIFF로 저장합니다. 축소 피라미드와 추가 페이지는 만들지 않습니다. 실행 날짜·시간 폴더에 TIFF와 원본 파일명/기술 정보를 담은 CSV를 함께 저장합니다.

```text
output/
└── 20260908_153000_123456/
    ├── anonymous_<ID1>.tiff
    ├── anonymous_<ID2>.tiff
    └── metadata.csv
```

폴더 이름은 로컬 시각 `YYYYMMDD_HHMMSS_ffffff`입니다. 끝의 마이크로초는 실행 간 이름 충돌을 줄입니다. 한 번의 GUI 일괄 실행은 한 폴더와 CSV를 공유하고, 다음 실행은 새 폴더를 생성합니다.

## 독립 함수 사용

**[`wsi_anonymizer.py`](wsi_anonymizer.py)**만 다른 프로젝트로 복사하면 됩니다. Python 3.10 이상과 다음 라이브러리가 필요합니다.

```shell
pip install openslide-python "openslide-bin>=4.0.1.2" numpy tifffile imagecodecs Pillow
```

```python
from wsi_anonymizer import anonymize_wsi

# 두 번째 인자는 TIFF 파일명이 아니라 출력 기본 폴더입니다.
result = anonymize_wsi("input/slide.ndpi", "output")
print(result["output_path"])
print(result["csv_path"])
```

여러 입력을 같은 폴더/CSV에 넣을 때는 하나의 `run_id`로 순차 호출합니다.

```python
from datetime import datetime
from wsi_anonymizer import anonymize_wsi

run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
for source in ["input/slide.svs", "input/slide.ndpi"]:
    anonymize_wsi(source, "output", run_id=run_id)
```

입력은 설치된 OpenSlide가 읽을 수 있는 형식에 따릅니다. SVS·NDPI와 일반 TIFF를 테스트합니다. 다채널/다중 초점면의 모든 데이터를 보존하는 변환은 아니며 OpenSlide의 2D RGB level 0을 출력합니다.

## CSV 항목

`metadata.csv`는 Excel에서 한글을 읽을 수 있도록 UTF-8 BOM과 표준 CSV 인용 규칙을 사용합니다. 유효한 기술 수치만 가져오며 알 수 없는 값은 빈칸입니다.

| 항목 | CSV 열 |
|---|---|
| 원본/출력 파일명 | `original_filename`, `output_filename` |
| 입력 확장자 | `source_format` |
| X·Y MPP (µm/pixel) | `mpp_x_um`, `mpp_y_um` |
| 가로·세로 픽셀 수 | `width_px`, `height_px` |
| 대물렌즈 배율 | `objective_power` |
| 원본 영상 레벨 수 / 출력 영상 수 | `source_level_count`, `output_pages` |
| 입력/출력 바이트 수 | `source_size_bytes`, `output_size_bytes` |
| 압축 방식 / 내보낸 시각 | `compression`, `exported_at` |
| 처리 상태 / 검증 타일 수 / 사용자 영상 검토 여부 | `status`, `verified_tiles`, `pixel_review_asserted_by_caller` |

환자명, 환자/검체 ID, 스캔 날짜, 스캐너 일련번호, 자유 텍스트는 메타데이터에서 추출하지 않습니다. **원본 파일명은 요청에 따라 그대로 기록하므로 파일명 자체에 개인정보가 있다면 CSV에도 포함됩니다.** Excel 수식으로 해석될 수 있는 `=`, `+`, `-`, `@`로 시작하는 파일명에는 앞에 작은따옴표를 붙입니다.

검증에 성공한 파일만 CSV 행을 추가합니다. 기존 CSV를 임시 파일로 재작성한 뒤 교체하며, CSV 저장 실패 시 해당 호출이 새로 만든 TIFF를 정리합니다. 같은 `run_id`에 대한 동시 쓰기는 지원하지 않으므로 순차 호출하세요. CSV 잠금 충돌은 데이터 손실 없이 오류로 처리합니다.

## Windows 프로그램

**`Launch_WSI.vbs`를 더블클릭**하거나 다음 명령으로 실행합니다.

```powershell
conda run -n yslee python -m pip install -r requirements.txt
conda run --no-capture-output -n yslee python app.py
```

`샘플 불러오기` → `전체 검사` → 출력 기본 폴더 선택 → `비식별 TIFF 내보내기` 순서입니다. `결과 폴더 열기`는 가장 최근에 완료된 실행 폴더를 엽니다. 단독 EXE는 아직 포함하지 않았습니다.

축소 레벨이 없는 대용량 단일 TIFF는 전체 영상의 메모리 로딩을 피하기 위해 썸네일을 생략합니다. 구조와 영역 읽기 검사는 수행합니다.

## 영상 처리와 검증

- 타일로 나누어 읽고 저장해 전체 WSI를 메모리에 올리지 않습니다. 타일은 내부 저장 단위이며 출력 영상/페이지는 1개입니다.
- 4GB 초과 출력을 지원하기 위해 BigTIFF를 사용하며 Deflate 무손실 압축을 적용합니다.
- 원본 메타데이터·라벨·매크로·썸네일·ICC·전용 태그·압축 바이트·미참조 영역은 TIFF에 복사하지 않습니다. 숫자 MPP만 TIFF 해상도로 기록할 수 있습니다.
- 모든 출력 타일의 픽셀 해시를 검증하고, TIFF에 영상 1개만 있는지와 허용된 구조 태그만 남았는지 검사합니다.
- 원본 파일은 보존하며 취소/실패 시 임시 TIFF를 정리합니다. 실패한 실행의 빈 날짜 폴더는 남을 수 있습니다.

영상에 직접 적힌 개인정보는 별도 검토 대상입니다. `redactions=[(x, y, 폭, 높이)]`로 level 0 좌표 영역을 흰색으로 가릴 수 있습니다. `pixels_reviewed=True`는 사용자가 남은 영상을 검토했다는 확인이며 자동 인증이 아닙니다. 자세한 정책은 [처리 정책](docs/processing_policy.md)을 참고하세요.

## 테스트

```powershell
conda run --no-capture-output -n yslee python tests/test_standalone.py
conda run --no-capture-output -n yslee python tests/smoke_gui.py
conda run --no-capture-output -n yslee python tests/integration_tiff.py
```

마지막 명령은 실제 샘플 전체를 처리하므로 시간이 걸립니다. 출력은 `output/<실행 시각>/`, 검증 기록은 `artifacts/single_tiff_validation.json`에 저장합니다. 과거 `output/clean_tiff/`의 피라미드 출력은 이전 버전 결과입니다.

명령행에서도 입력 파일과 출력 **폴더**를 지정합니다.

```powershell
conda run --no-capture-output -n yslee python wsi_anonymizer.py input.ndpi output
```
