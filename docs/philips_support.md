현재 1.9.0은 Philips 고유 압축을 유지하여 .isyntax로 내보냅니다. SDK 원본 블록 복사, 메타데이터 재작성, 검증과 사용법은 [원본 유지 가이드](native_philips.md)를 참고하세요. GUI 기본값은 원본 유지이며 아래 1.8.2 설명은 TIFF 변환 옵션에 해당합니다.

JPEG 2000 lossless (v1.8.2)
-------------------------
API: anonymize_wsi(input_path, output_dir, compression="jpeg2000", pyramid=True)
Philips GUI default: auto_jpeg2000 (Philips JPEG 2000 lossless; other compatible inputs preserve JPEG).
Existing auto mode continues to mean Philips Deflate. JPEG Q90 remains an explicit lossy option.
Output uses Aperio-compatible tiled BigTIFF with JPEG 2000 codestreams (compression 33005),
reversible wavelet transform and reversible color transform. Generated pyramid levels use the same codec.
Lossless means exact preservation of SDK/OpenSlide decoded RGB, not Philips original internal samples.
Full base tile pixel hashes are verified after decoding; all pyramid tiles are decoded and hashed.
JPEG 2000 may be slower; size and performance depend on image content. Generic TIFF readers may not support this Aperio compression tag.

# Philips iSyntax / i2syntax — 1.8.2 내부 연구용 배포

**이 배포본은 다른 Windows 10/11 x64 연구용 PC에서 Python·Conda·SDK를 별도로 설치하지 않고 실행하도록 구성했습니다.** ZIP을 모두 풀고 `WSI/WSI_Anonymization.exe`를 실행합니다. 옆의 `philips` 폴더를 함께 유지하세요. `philips/SDK.zip`은 보관용 SDK 원본이므로 실행을 위해 다시 풀 필요가 없습니다.

Windows용 SDK는 `python37.dll`을 요구합니다. 기존 Conda 환경을 복사하지 않고 공식 Python 3.7.9 임베디드 배포본과 NumPy 1.21.6 / Pillow 9.5.0 Windows wheel, 제공된 SDK의 원본 DLL/PYD로 전용 런타임을 만들었습니다. SDK는 이 런타임의 별도 프로세스에서 실행됩니다. 시스템 Python, Conda, PATH를 설정하지 않습니다. 인터넷 연결도 필요하지 않습니다.

제공된 `philips_bridge.zip`의 프로세스 분리 구조와 SDK DLL 경로 처리를 참고했습니다. ZIP이 참조하는 OpenPhi는 포함되어 있지 않았습니다. PyPI OpenPhi 2.1.0을 조사했으나 `.isyntax` 확장자만 허용하고 라벨/매크로가 항상 있다고 가정하며 배율을 40으로 고정합니다. 이번 구현은 실제 SDK를 직접 호출하여 `.i2syntax`, 부속 이미지 없는 입력, 배율 미확인을 처리합니다. 최종 실행에는 OpenPhi가 필요하지 않습니다.

## 프로그램 사용

1. `.isyntax` 또는 `.i2syntax`를 추가합니다.
2. Philips 파일을 추가하면 기존 `원본 JPEG 압축 유지` 선택은 **형식별 자동 · Philips JPEG 2000 무손실**로 바뀝니다. 목록 아래 안내와 압축 설정에서 확인할 수 있습니다.
3. Philips 출력 용량을 줄이려면 **형식별 자동 · Philips JPEG Q90 (손실)**를 선택합니다. Philips만 JPEG로 재압축하고 호환 SVS/NDPI는 기존 압축을 유지합니다. JPEG 품질 90 / 4:2:0은 추가 손실 압축입니다. `JPEG 재압축` 항목은 선택한 모든 입력을 JPEG로 재압축합니다.
4. 검사 또는 내보내기를 실행합니다. TIFF/CSV 선택, 익명 파일명, MPP, ICC, 날짜·시간 출력 폴더 설정은 기존과 같습니다.

Philips **iSyntax 고유 압축**과 JPEG/JPEG 2000은 서로 다릅니다. 원본 iSyntax 압축 블록을 현재 표준 TIFF에 그대로 넣으면 이 프로그램의 OpenSlide 읽기 경로와 호환되지 않습니다. `JPEG Q90`은 고유 압축 보존이 아닌 새 압축 옵션입니다. [Philips 압축 방식 설명](https://www.philips.com/c-dam/b2bhc/master/sites/pathology/resources/isyntax-paper-20200518.pdf), [OpenSlide 지원 형식](https://openslide.org/formats/).

SDK가 파일을 읽지 못하면 해당 파일을 실패로 표시하고 다음 파일을 처리합니다. 실패한 입력에서 성공한 익명화 결과를 만들거나 원본을 수정하지 않습니다.

## 함수 호출

메인 Python 환경에서 사용합니다.

```python
from wsi_anonymizer import anonymize_wsi

result = anonymize_wsi(
    "slide.i2syntax", "output",
    compression="jpeg2000",  # SDK 표시 RGB를 JPEG 2000 무손실 저장
    include_filename=False,
    preserve_icc=False,
)
```

Philips에서 `compression="preserve"`로 TIFF를 요청하면 명확한 오류를 반환합니다. API는 `preserve`, `lossless`, `jpeg`, `jpeg2000`을 받습니다. GUI의 `auto`와 `auto_jpeg`는 파일별로 실제 압축 값을 선택하는 UI 옵션입니다. CSV 전용 호출은 `export_image=False`로 사용할 수 있습니다. JPEG 출력은 반환값 `compression="jpeg-reencoded-q90"`, `additional_lossy_compression=True`, `jpeg_quality=90`으로 표시되며 CSV에도 압축 방식이 기록됩니다. 타일 검증 통과는 재압축 결과의 무결성 검증이며 원본 픽셀과 동일하다는 뜻이 아닙니다.

다른 프로젝트에서는 `wsi_anonymizer.py` 옆에 배포본의 `philips` 폴더를 함께 복사하면 동봉 런타임을 사용합니다. 별도 설치한 SDK 환경을 명시적으로 사용하려는 개발자만 다음 환경 변수를 지정합니다. 이 경우에는 `philips_bridge` 소스 폴더도 필요합니다.

```powershell
$env:PHILIPS_PYTHON = 'C:\path\to\philips-sdk-py37\python.exe'
python app.py
# EXE도 같은 환경 변수를 사용합니다.
```

명시한 `PHILIPS_PYTHON`이 없으면 EXE/모듈 옆의 `philips/python.exe`를 우선 사용합니다. 동봉 런타임이 없는 소스 개발 환경만 기존 `%USERPROFILE%\.conda\envs\philips-sdk-py37\python.exe`를 탐색합니다. 브리지는 표준 입력/출력과 Windows 공유 메모리를 사용하며 네트워크 서버를 열지 않습니다. 원본 메타데이터나 영상 타일을 통신 로그로 저장하지 않습니다.

## 소스로 개발할 때만 별도 환경 준비

완성된 연구용 ZIP 사용자에게는 필요 없는 절차입니다. 별도 개발 환경이 필요하면 다음과 같이 준비할 수 있습니다.

```powershell
conda create -n philips-sdk-py37 python=3.7.9 pip -y
conda activate philips-sdk-py37
python -m pip install -r requirements-philips.txt
# SDK Modules 아래 각 모듈의 setup.py가 있는 폴더를 지정합니다.
python -m pip install 'C:\SDK\Modules\philips.pathologysdk.pixelengine.2.0-L1'
python -m pip install 'C:\SDK\Modules\philips.pathologysdk.softwarerenderbackend.2.0-L1'
python -m pip install 'C:\SDK\Modules\philips.pathologysdk.softwarerendercontext.2.0-L1'
```

SDK의 DLL과 해당 모듈이 모두 설치되어야 합니다. SDK 폴더명에 다른 Python 버전을 붙여도 바이너리의 Python 3.7 요구 사항은 바뀌지 않습니다.

## 출력의 의미와 익명화 범위

- SDK의 **display view, 8비트 RGB**를 읽고 선택한 JPEG 또는 Deflate로 저장합니다. Deflate의 무손실은 **SDK가 렌더링한 RGB에 추가 압축 손실이 없다**는 뜻입니다. 원본의 내부 9비트 표현이나 모든 채널/초점면을 보존한다는 뜻이 아닙니다.
- SDK 표시 영역을 출력합니다. 원시 영역과 표시 영역의 경계가 다를 수 있습니다. TIFF 기술 JSON과 CSV의 `source_representation`, `source_origin_x_px`, `source_origin_y_px`, API의 `philips_display_origin`으로 표현과 시작 좌표를 확인합니다. 출력 피라미드는 익명화된 기본 TIFF에서 생성합니다.
- MPP는 SDK의 실제 단위가 확인되는 값만 보존합니다. `source_vendor=philips`를 기록합니다. SDK에서 확인되지 않은 objective-power는 비워 두며 40배로 추정하지 않습니다. 출력 파일의 `openslide.vendor=aperio`는 TIFF 호환 형식입니다.
- 원본 XML, 바코드, 장비 일련번호, 스캔 날짜, 라벨/매크로는 복사하지 않습니다. Philips XML 필드의 실제 원본 값이나 개별 환자 필드를 탐지·비교한 것은 아닙니다. 익명화 내역에서는 TIFF 태그 비교 불가와 Philips 원본 XML 제외 정책을 구분합니다.
- ICC는 기본 제외입니다. 선택 시 SDK가 제공한 원본 RGB ICC를 복사하며 기존과 같이 별도 검토 필요로 표시합니다. 프로파일 내부의 식별 정보를 자동 제거했다고 주장하지 않습니다.
- 조직 영상 안에 직접 찍힌 식별자는 자동 삭제하지 않습니다. 원본 파일명 유지/CSV 포함 옵션도 별도로 적용됩니다.

## 제공 샘플 확인

`20260511_124345.i2syntax`: SDK에서 열기·조직 영역·썸네일 읽기 성공. 원시 영역 52,000 × 22,149, 표시 영역 51,996 × 22,145, 표시 시작 좌표 (2, 2), MPP X/Y 약 0.2479516602 µm. 부속 이미지 없음. 확인된 배율 없음. ICC 16,894바이트.

원본 105,055,621바이트 → Deflate 피라미드 TIFF 929,985,707바이트 / JPEG Q90 피라미드 TIFF 72,034,064바이트(ICC 제외). JPEG 결과는 새 동봉 런타임으로 생성했으며 5개 레벨과 전체 5,697개 타일을 검증했습니다. 용량은 영상 내용에 따라 달라집니다.

`20260514_084959.i2syntax`: 새로 올린 211,555,284바이트 파일은 동봉 SDK로 정상 읽혔습니다. 표시 영역 187,996 × 83,747, 10개 레벨, 30개 영역 읽기와 썸네일 생성 성공입니다. 이전 175,572,357바이트 파일에서 발생했던 DICOM 블록 오류는 재업로드 후 발생하지 않았습니다. 새 두 번째 파일은 읽기 검사를 완료했으며 전체 TIFF 변환 검증은 아직 수행하지 않았습니다.

## 배포

사용자가 지정한 **동일 기관 내부 연구용 배포**로 SDK를 동봉했습니다. `philips/EULA.txt`와 `philips/SDK.zip`에 제공된 Windows SDK 및 모든 제공 문서를 원본 바이트 그대로 포함합니다. 런타임의 SDK DLL/PYD도 수정하지 않았습니다. SDK 사용 조건은 함께 제공되는 연구용 EULA를 따릅니다. 이 빌드는 외부 공개 배포용으로 표시하지 않습니다.

런타임 원본 다운로드와 구성 파일의 SHA-256은 `philips/RUNTIME.json` 및 `BUILD_INFO.json`에 기록합니다. `tools/build_philips_runtime.py`로 런타임을 구성한 뒤 `tools/build_release.py`로 연구용 ZIP을 만듭니다.

참고: [OpenPhi 원본 프로젝트](https://gitlab.com/BioimageInformaticsGroup/openphi), [OpenPhi 2.1.0](https://pypi.org/project/openphi/2.1.0/).
