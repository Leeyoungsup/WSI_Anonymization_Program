# SVS·NDPI 원본 형식 저장 · 1.10.0

GUI의 **1. 원본 형식 유지**를 선택하면 호환 SVS는 `.svs`, NDPI는 `.ndpi`, Philips는 `.isyntax`로 저장합니다. 형식별로 조직 압축과 기존 조직 피라미드 단계를 유지하고, 원본 설명문·식별 메타데이터·라벨·매크로·참조되지 않는 원본 바이트를 제외합니다. 파일 확장자만 바꾸는 기능이 아닙니다.

```python
from wsi_anonymizer import anonymize_wsi

result = anonymize_wsi(
    "slide.ndpi", "output",
    compression="native",
    include_filename=False,
    rename_output=True,
)
print(result["output_path"])
```

독립 함수의 구현은 `wsi_anonymizer.py`에 포함되어 있습니다. SVS·NDPI에는 기존 OpenSlide/tifffile/imagecodecs 의존성을 사용하며 Philips에는 기존 SDK 브리지가 필요합니다. 기존 `compression="preserve"`는 계속 TIFF를 출력합니다. `native`는 원본 해상도 단계와 보정 정보를 유지하므로 `pyramid=False`, `preserve_mpp=False`, 픽셀 마스킹과 함께 사용할 수 없습니다.

## SVS

- 현재 지원: Aperio로 인식되는 호환 baseline JPEG 타일 SVS. JPEG 2000 등 다른 원본 코덱의 SVS native 저장은 이번 버전에 포함하지 않습니다.
- 원본 조직 타일의 JPEG 코딩 데이터를 재사용하고 APP/COM 부가정보를 제외합니다. 조직 피라미드 레벨만 유지하며 축소 레벨을 새로 만들지 않습니다.
- TIFF 태그는 허용된 기술 정보만 다시 기록합니다. 원본 썸네일·라벨·매크로는 복사하지 않으며 `get_thumbnail()`은 조직 피라미드에서 만듭니다.
- 모든 출력 타일의 압축 데이터 해시와 디코딩을 검사합니다. OpenSlide의 Aperio 인식, 레벨·배율·MPP·ICC 선택 결과, 모든 레벨의 표본 픽셀 일치를 확인한 뒤 게시합니다.

## NDPI

- 현재 지원: little-endian NDPI, 단일 초점면, self-contained baseline 8비트 4:4:4 JPEG, 호환 restart 구조. 지원하지 않는 레이아웃은 오류로 처리하며 임의로 TIFF로 바꾸지 않습니다.
- 각 조직 레벨의 JPEG 헤더에서 APP/COM을 제거하고 압축 스캔을 그대로 스트리밍 복사합니다. JPEG restart 위치 인덱스와 NDPI 전용 64비트 오프셋 디렉터리를 새로 작성합니다.
- 스캐너 모델·일련번호·스캔 날짜·Reference·프로퍼티 맵·커버리지 맵 등은 복사하지 않습니다. 새로 만든 필드는 JPEG 해석과 영상 크기·배율·MPP에 필요한 항목과 고정 제조사 이름 `Hamamatsu`로 제한합니다.
- 모든 출력 JPEG 바이트의 해시, 인덱스·기술 필드의 정확한 값과 태그 허용 목록을 검사합니다. OpenSlide가 Hamamatsu로 인식하고 모든 레벨의 표본 픽셀이 원본과 일치하는지도 확인합니다. **모든 픽셀을 디코딩한 검증은 아닙니다.** `all_output_tiles_verified=False`로 보고합니다.
- 현재 OpenSlide NDPI 경로에서는 ICC 보존을 검증할 수 없습니다. 원본에 ICC 태그가 있고 보존을 요청하면 명시적으로 거부합니다. ICC가 없는 입력은 다른 파일과 같은 목록에서 처리할 수 있습니다.

## 검증과 크기

제공된 샘플의 기본 ICC 제외 결과:

| 입력 | 원본 bytes | 출력 bytes | 조직 단계·검증 |
| --- | ---: | ---: | --- |
| SVS | 1,121,916,033 | 1,066,092,567 | 원본 조직 레벨 유지, 모든 JPEG 타일 검증, 43개 표본 영역 일치 |
| NDPI | 2,111,622,750 | 2,111,362,048 | 원본 조직 레벨 유지, 전체 JPEG 바이트 검증, 88개 표본 영역 일치 |

`tests/test_native_formats.py`는 합성 식별 정보의 제거, 비정상 JPEG 스캔의 거부, 4GiB를 넘는 NDPI 파일 오프셋의 읽기/쓰기, CSV·이름 충돌·취소·실패 시 정리를 검사합니다. 4GiB 검증은 작은 JPEG를 큰 오프셋에 배치한 sparse 파일로 수행하며, 4GiB 이상 단일 JPEG 전체를 내보낸 시험은 아닙니다.

기관 내부 전용 뷰어 전체와의 호환성을 검증한 것은 아닙니다. 현재 재열기 검증 기준은 OpenSlide입니다. 조직 영상 자체에 들어 있는 식별자는 직접 검토해야 하며, 선택적으로 보존한 ICC와 원본 파일명도 별도 검토 대상입니다.

포맷 참고: [OpenSlide Aperio](https://openslide.org/formats/aperio/), [OpenSlide Hamamatsu](https://openslide.org/formats/hamamatsu/).
