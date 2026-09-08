# 샘플 구조 검사

현재는 읽기 전용 검사 단계입니다. 익명화 엔진과 GUI는 아직 구현하지 않았습니다.

## 실행

```powershell
conda run -n yslee python tools/inspect_samples.py data
```

보고서는 `artifacts/sample_inventory.json`에 저장됩니다. 원본 파일명과 메타데이터 값을 제외하고 구조, 태그 이름, 영상 크기, 읽기 결과를 기록합니다. `data/`와 `artifacts/`는 Git에서 제외합니다.

확인한 환경: Python 3.12.12, openslide-python 1.3.1, openslide-bin 4.0.0.11, tifffile 2025.12.20. 검사 도구에서 Windows DLL 경로를 설정하므로 기존 환경을 그대로 사용합니다.

## 2026-09-08 확인 결과

| 항목 | SVS | NDPI |
|---|---|---|
| 파일 크기(십진 GB) | 1.12 | 2.11 |
| 최대 영상 크기 | 110,562 × 61,468 | 126,720 × 96,768 |
| OpenSlide 레벨 수 | 3 | 8 |
| TIFF 디렉터리 수 | 6 | 4 |
| 부속 이미지/기타 영상 | label, macro, thumbnail | SourceLens=-2인 600 × 205 영역 지도 |
| 영역 읽기 | 9개 성공 | 24개 성공 |

각 OpenSlide 레벨의 좌상단·중앙·우하단에서 최대 128 × 128 영역을 읽고 썸네일 생성을 검사했습니다. SVS 부속 이미지도 디코딩했습니다. 전체 영상 무결성 검사나 개인정보 부재 검증은 아닙니다. SubIFD는 존재 여부만 기록하며 이번 샘플에는 없습니다.

SVS에는 날짜·시간·스캐너 ID 관련 메타데이터 키가 있습니다. NDPI에는 Reference, 스캐너 식별 태그, ASCII 메타데이터 블록 및 추가 전용 태그가 있습니다. 이는 검토 대상 후보이며 실제 환자정보 존재 여부를 판정한 결과는 아닙니다.

이번 NDPI는 OpenSlide 부속 이미지 목록이 비어 있어도 TIFF 내부에 영역 지도가 있습니다. 따라서 전체 디렉터리와 전용 태그까지 검사해야 합니다. OpenSlide가 제공하는 레벨 수는 실제 저장된 디렉터리 수와 다릅니다.

## 다음 구현

1. SVS·NDPI별 메타데이터 보존/제거 정책 수립.
2. 사본에만 적용하는 형식별 익명화 엔진 구현. 삭제 데이터의 바이트 잔존까지 고려.
3. 압축 영상 데이터 보존, 재열기, 영상 구조 비교, 잔존 식별정보 검사.
4. PySide6 일괄 처리 UI와 Windows 실행 파일 배포.

이번 두 파일로 다른 스캐너 변형, 4GB 초과 NDPI, 다중 초점면, NDPI 라벨·매크로 제거까지 검증할 수는 없습니다. 추가 샘플 검증에 따라 지원 범위를 확정합니다.

형식 참고: [Aperio SVS](https://openslide.org/formats/aperio/), [Hamamatsu NDPI](https://openslide.org/formats/hamamatsu/).
