# 원본 JPEG 압축 유지 TIFF 검증 — 2026-09-08

`yslee` 환경에서 실제 샘플 두 개를 `output/20260908_131811_451238/`에 저장했습니다. 최대 해상도 1장, SubIFD 0개, JPEG 압축의 BigTIFF입니다. JPEG 인코더를 호출하지 않았으며 원본 압축 영상 데이터를 재사용했습니다.

| 항목 | SVS | NDPI |
|---|---:|---:|
| 원본 바이트 | 1,121,916,033 | 2,111,622,750 |
| 출력 바이트 | 995,229,102 | 2,083,751,677 |
| 출력 크기 (십진 GB) | 0.995 | 2.084 |
| 영상 크기 | 110562 × 61468 | 126720 × 96768 |
| 출력 타일 크기 | 256 × 256 | 3840 × 16 |
| 전체 읽기/무결성 검증 타일 수 | 104,112 | 199,584 |
| OpenSlide 원본/출력 픽셀 비교 영역 | 25 | 25 |
| 변환·검증 시간 (초) | 21.9 | 52.6 |

SVS는 원래 JPEG 타일을 유지했습니다. NDPI는 원래 3840 × 8 restart 구간 두 개를 세로로 묶어 TIFF의 16배수 타일 규격을 만족시켰습니다. 압축 영상 데이터와 양자화 테이블은 유지하고 JPEG 높이와 restart 번호만 수정했습니다. NDPI는 타일마다 헤더가 추가되므로 용량 감소 폭이 작습니다.

결과 파일:

- SVS: `anonymous_7b4ff7d22f2a4d589037e2dba8156e14.tiff`
- NDPI: `anonymous_fe5e755ad9eb4de9b186720bf999340a.tiff`
- CSV: `metadata.csv` — 두 원본 파일명과 MPP, 크기 등 기술 정보, `compression=jpeg-preserved`
- 기계 판독 기록: `artifacts/preserved_tiff_validation.json`

모든 출력 타일의 압축 바이트를 기록 당시 SHA-256과 비교했고 전체 타일을 디코딩했습니다. OpenSlide로 두 원본/출력 각각 25개 영역의 RGBA 픽셀 일치를 확인했습니다. 두 원본 전체 파일 SHA-256은 변환 전후 동일합니다. 원본 개인정보 TIFF 태그·추가 영상·JPEG APP/COM·파일의 미참조 영역은 출력하지 않습니다. 원본 픽셀 자체에 식별자가 없는지는 사용자 검토 대상이며 결과 상태는 `metadata_clean_pixel_review_required`입니다.

자동 검증:

- 기존 명시적 lossless 경로 10개 테스트 통과: 픽셀 마스크, 취소, CSV 잠금/저장 실패, 덮어쓰기 방지, 독립 모듈 실행 등.
- 압축 유지 경로 6개 테스트 통과: 인코더 호출 금지, 원본/출력 압축 영상 데이터·전체 픽셀 일치, APP/COM/후행 식별자 제거, NDPI restart 재배치, 손상 출력·취소 정리, 지원하지 않는 압축 거부, 독립 CLI 기본값.
- GUI 테스트 통과: 두 실제 샘플 검사, JPEG TIFF 일괄 내보내기와 날짜 폴더/CSV, 검토 확인 전달, 취소, 오류 복구, 원본 전체 해시 보존.

형식 근거: [OpenSlide Aperio](https://openslide.org/formats/aperio/), [OpenSlide Hamamatsu](https://openslide.org/formats/hamamatsu/). NDPI restart 인덱스/헤더 해석은 설치된 tifffile 2025.12.20을 사용했습니다.
