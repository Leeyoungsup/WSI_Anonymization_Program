# Windows EXE 1.10.1 내부 연구용 검증

2026-09-11: GUI, `anonymize_wsi()`, 워커 어댑터, CLI의 `preserve_icc` 기본값을 True로 변경했습니다. CLI `--no-preserve-icc` 및 API/GUI의 명시적 제외는 계속 지원합니다. ICC가 없으면 생성하지 않으며, 원본 TIFF 기본 페이지에 ICC가 있지만 리더에서 제공하지 못하면 오류로 안내합니다. ICC 포함 시 기존 별도 검토 상태를 유지합니다.

- `tests/test_icc_defaults.py`: API/CLI 기본값의 ICC 원문 일치, 명시적 제외, 보고서 및 어댑터 기본값을 검증했습니다.
- `tests/test_export_options.py`, `tests/test_native_formats.py`: GUI 기본 체크 상태, CSV 옵션, 읽기/보존 불가 ICC의 오류 처리와 기존 native 경로 검증을 통과했습니다.
- 최종 EXE `tests/test_release.py`: 워커 옵션을 생략해도 ICC가 보존되며 원문이 일치하고, `preserve_icc=False`로 제외할 수 있음을 확인했습니다. 기존 TIFF/JPEG/JPEG 2000·CSV·취소도 통과했습니다.
- `tests/test_philips_release.py`: ICC 옵션을 생략한 두 Philips 샘플의 native 저장·표본 픽셀 일치·재열기를 확인했습니다. 동봉 런타임을 Python/Conda 없는 PATH와 가짜 홈에서 시험했습니다.
- `tests/test_native_batch_gui.py --frozen`: 기본 체크 상태로 실제 SVS·NDPI·Philips를 한 목록에서 저장했습니다. ICC가 있는 SVS/Philips는 보존되고, ICC가 없는 NDPI는 추가하지 않았습니다. 각 파일의 43/88/24개 표본 픽셀 일치와 원본 SHA256 미변경을 확인했습니다.
- 최종 EXE 내부 GUI·워커·어댑터·독립 엔진의 바이트코드를 현재 소스와 비교하고 ZIP CRC 및 소스/실행 파일/런타임 해시를 검증했습니다.

## 1.10.0 이전 검증 기록

2026-09-11: `compression="native"`와 GUI 1번에 호환 JPEG SVS·NDPI 원본 형식 저장을 추가했습니다. 기존 SVS→TIFF/NDPI→TIFF 기능과 Philips native 기능은 유지합니다. 지원 조건과 검증 범위는 `native_svs_ndpi.md`를 참고하세요.

- `tests/test_native_formats.py`: 합성 SVS·NDPI를 OpenSlide로 재열어 실제 벤더·레벨·배율·MPP·픽셀을 대조했습니다. JPEG COM과 TIFF/private 태그에 넣은 합성 식별 문자열의 제거, 라벨 제외, CSV 원본명 제외, 파일명 충돌, 취소, 잘못된 JPEG 스캔·옵션·지원하지 않는 NDPI ICC 처리, 미완성 파일 정리를 통과했습니다. NDPI 4GiB 초과 오프셋은 sparse 입력의 작은 JPEG로 검증했으며 단일 4GiB 초과 JPEG 전체 시험은 아닙니다.
- `tests/test_native_batch_gui.py`와 `--frozen`: 제공된 SVS·NDPI·Philips 첫 샘플을 한 목록/날짜 폴더로 원본 형식 내보내기 했습니다. 최종 EXE에서 각각 `aperio-svs`, `hamamatsu-ndpi`, `philips-isyntax`로 완료했습니다. 원본 SHA-256은 전후 동일하며 ICC 포함 SVS 1,079,205,863 bytes, NDPI 2,111,362,048 bytes, ICC 포함 Philips 105,055,028 bytes였습니다. 각 입력의 43/88/24개 표본 영역 일치, 원본 조직 레벨·압축 유지, 재인코딩·추가 레벨 생성 없음, 공통 CSV를 확인했습니다.
- SVS는 모든 출력 JPEG 타일의 압축 데이터 해시와 디코딩을 검증합니다. NDPI는 모든 JPEG 바이트 해시와 새 인덱스·기술 필드를 검증하고 모든 OpenSlide 레벨에서 표본 영역을 디코딩합니다. NDPI 전체 픽셀 디코딩을 완료했다고 보고하지 않습니다.
- `tests/test_native_gui.py`, `tests/test_export_options.py`, `tests/test_audit_comparison_gui.py`, `tests/test_preserved.py`: 지원 항목, 설명 창, 파일명/ICC/MPP/CSV 조합, 원본 값의 화면 전용 표시, 기존 JPEG 유지 경로를 검증했습니다.
- 최종 EXE의 `tests/test_release.py`, `tests/test_philips_release.py`: 기존 TIFF/JPEG/Deflate/JPEG 2000·취소·원본 무변경과 동봉 Philips 런타임/두 실제 샘플의 native 출력 재검사·미리보기를 통과했습니다. Philips 시험은 Python/Conda 없는 PATH와 가짜 홈에서 수행했습니다.
- 최종 EXE 내부 GUI·워커·엔진의 바이트코드와 상수·시그니처를 현재 소스와 대조했습니다. ZIP CRC, 소스·EXE·런타임 SHA256, 설명 문서 일치를 확인했습니다. ZIP 내부 최장 경로는 95자입니다.

실제 새 Windows 설치 PC/VM 또는 모든 제조사 전용 뷰어의 호환성을 시험한 것은 아닙니다. 조직 픽셀 속 식별자와 선택적으로 보존한 ICC/원본 파일명은 별도 검토 대상입니다.

## 1.9.1 이전 검증 기록

GUI 저장 방식을 원본 형식 유지 / 원본 압축 유지 TIFF / 무손실 TIFF 세 가지로 변경했습니다. 형식·TIFF 헤더를 사전 확인해 목록 전체에서 지원하지 않는 항목을 선택 불가로 표시하고 ⓘ에서 이유를 설명합니다. 원본 형식 유지는 현재 Philips만 지원하며 `.i2syntax`도 `.isyntax`로 저장합니다. 무손실 TIFF는 모든 입력에 JPEG 2000을 적용합니다. 자세한 내용은 `storage_modes.md`를 참고하세요.

2026-09-11 최종 1.9.1 검증:
- `tests/test_native_gui.py` 및 `--frozen`: 정확히 세 선택지, 실제 SVS/NDPI 헤더 사전 확인, Philips·TIFF·비압축 TIFF·혼합 목록의 선택 제한, 프로그램 코드로 비활성 항목 선택 시 차단, ⓘ 설명, 목록 초기화, CSV 전용 상태를 확인했습니다. 실제 워커의 Philips 원본 저장 / JPEG 유지 TIFF / JPEG 2000 무손실 TIFF를 실행하고 무손실 픽셀 일치를 검증했습니다. 혼합 목록의 전체 Philips 무손실 TIFF 변환은 실행하지 않았으며 옵션 전달과 선택 제한을 확인했습니다.
- `tests/test_export_options.py`, `tests/test_philips_gui.py`, `tests/test_audit_comparison_gui.py`: CSV 조합, 파일명·MPP·ICC 설정, 정보 창, 익명화 전후 원본 값의 화면 전용 표시와 메모리 초기화를 통과했습니다.
- `tests/test_release.py`: 최종 EXE의 검사, JPEG 유지, Deflate·JPEG 2000, ICC, CSV 전용, 취소, 원본 무변경 검증을 통과했습니다.
- `tests/test_philips_release.py`: Python/Conda 경로 없는 PATH와 가짜 사용자 홈에서 동봉 런타임을 사용했습니다. 두 실제 샘플의 native 전체 내보내기, 전체 압축 블록 검증 결과, ICC 포함 표본 픽셀 일치, 출력 재검사·미리보기, CSV 전용, 잘못된 입력 처리를 통과했습니다.
- offscreen으로 설정 화면과 사용 불가 항목을 렌더링해 확인했습니다. 최종 EXE 내부 GUI/워커/엔진의 문자열 상수를 현재 소스와 대조했습니다. ZIP CRC, 실행 파일 동일성, 원본 소스·동봉 SDK 런타임 해시, SHA256을 확인했습니다. ZIP 내부 최장 경로는 95자입니다.

실제 새 Windows 설치 PC/VM에서 수행한 시험은 아닙니다. 외부 프로그램의 모든 뷰어 조합이나 모든 WSI 변형을 보장하지 않습니다. 영상 속 식별자와 선택적으로 보존한 ICC는 별도 검토 대상입니다.

## 1.9.0 이전 검증 기록

1.9.0은 Philips 고유 압축을 보존한 .isyntax 저장과 목적별 간단한 UI를 추가합니다. `tests/test_native_philips.py`에서 두 샘플의 전체 압축 블록, 웨이블릿 설정, XML 필드 허용 목록, 크기·해상도 단계, ICC 포함/제외, CSV, 취소, 이름 충돌, 원본 미변경을 검증했습니다. `tests/test_native_gui.py`에서 Philips와 TIFF 혼합 작업의 기본 설정 전달 및 올바른 확장자를 확인했습니다. 저장 코덱은 hulsken2/Q2를 유지합니다. 전체 압축 블록은 대조하지만 디코딩은 모든 레벨의 표본 영역만 검사합니다. ICC 포함 시 표본 표시 픽셀도 일치합니다. 용량·실행 시간과 범위는 `native_philips.md`를 참고하세요.

최종 1.9.0 EXE에서도 `tests/test_philips_release.py`로 두 샘플 전체 native 내보내기와 생성 파일 재검사·미리보기를 검증했습니다. 기존 Python/Conda 경로를 제거한 PATH와 가짜 사용자 홈에서 동봉 런타임을 사용했습니다. `tests/test_native_gui.py --frozen`은 실제 EXE의 Philips/TIFF 혼합 작업을 통과했습니다. `tests/test_release.py`의 기존 TIFF/JPEG 2000·ICC·CSV·취소 회귀 검증도 통과했습니다. 실제 새 Windows 설치 PC/VM에서 실행한 시험은 아닙니다.

`tests/test_native_header.py`는 허용되지 않은 환자 필드, 예기치 않은 ICC 값, 양자화 설정 불일치 및 XML 엔티티 선언을 각각 해당 사유로 거부함을 확인했습니다.

아래는 이전 TIFF 릴리즈 검증 기록입니다.

1.8.2 GUI: 헤더·빈 목록·상태줄에 Philips를 표시하고 동봉 런타임 안내를 추가했습니다. 압축 이름을 줄이고 선택란 아래에 파일 형식별 처리 방식과 JPEG 추가 손실 여부를 항상 표시합니다. 화면을 offscreen으로 렌더링하여 배치를 확인하고 기존 내보내기 옵션·원본 값 비저장 GUI 검사를 통과했습니다.

재업로드된 두 번째 Philips 샘플(211,555,284바이트)은 같은 SDK로 정상 읽혔습니다. 187,996 × 83,747, 10개 레벨, 30개 영역 읽기 및 썸네일 생성 성공입니다. 이전 파일의 실패 기록은 과거 입력에 대한 것입니다. 새 두 번째 샘플의 전체 TIFF 변환은 아직 검증하지 않았습니다. 오류 처리 테스트는 실제 정상 샘플 대신 별도의 잘못된 합성 입력을 사용합니다.

배포 ZIP: `release/WSI_Anonymization-1.8.2-Windows-x64-Research.zip`.

1.8.2은 공식 Python 3.7.9 임베디드 배포본, NumPy 1.21.6 / Pillow 9.5.0 Windows wheel과 제공된 Windows 연구용 SDK의 원본 DLL/PYD를 동봉합니다. 기존 Conda 환경 전체를 복사하거나 실행 시 참조하지 않습니다. SDK 원본 Windows 배포 파일·문서는 `philips/SDK.zip`, EULA는 `philips/EULA.txt`, 구성과 해시는 `philips/RUNTIME.json`에 포함합니다.

`tests/test_portable_philips.py`: OS System32만 있는 PATH, 기존 Conda가 없는 가짜 사용자 홈, 격리된 임베디드 Python에서 샘플 열기 성공. 실제 프로세스의 로드 모듈을 조사해 Python/SDK DLL이 동봉 경로에 있으며 Conda/Anaconda DLL이 로드되지 않음을 확인했습니다. 정적 PE 의존성 검사에서 외부 의존성은 Windows 기본 시스템 DLL/API 세트뿐입니다. 새 Windows OS를 별도 설치한 VM 검증은 수행하지 않았습니다.

`tests/test_jpeg_export.py`: JPEG Q90 손실 압축 표시, 개인정보 표식 제외, 표준 피라미드와 전체 타일 디코딩/압축 바이트 해시 검증, OpenSlide 읽기, CSV 압축 방식 기록과 취소 정리를 확인했습니다. 실제 첫 Philips 샘플은 동봉 런타임으로 72,034,064바이트 JPEG TIFF(5개 레벨, 5,697개 검증 타일)로 변환했습니다. 원본은 105,055,621바이트이며 Deflate 결과는 929,985,707바이트입니다. JPEG는 추가 손실 압축으로 원본 픽셀 동일성을 주장하지 않습니다. 결과 기록: `artifacts/philips_jpeg_validation.json`.

이하 1.7.0 및 이전 버전의 검증 이력입니다. 이전 버전의 SDK 미동봉/별도 환경 조건은 1.8.2 내부 연구용 ZIP에는 적용되지 않습니다.

1.7.0 Philips: 기존 Python 3.7.9 SDK 환경의 핵심 DLL/PYD 6개가 제공 ZIP의 Windows SDK와 SHA-256으로 일치함을 확인했습니다. 첫 i2syntax 샘플의 51,996 × 22,145 SDK 표시 RGB를 Deflate 피라미드 TIFF로 변환하고 모든 출력 타일 검증, 25개 원본/출력 영역 픽셀 일치를 확인했습니다. 전체 결과는 `artifacts/philips_conversion_validation.json`입니다. 두 번째 샘플은 SDK 2.0의 내부 DICOM 블록 오류로 열기 실패하며 지원 성공으로 집계하지 않습니다.

최종 EXE에서 PATH를 Windows System32로 제한하고 `PHILIPS_PYTHON`으로 별도 SDK 인터프리터를 지정해 Philips 검사·썸네일·CSV 전용·읽기 실패 처리를 확인했습니다. 기존 frozen GUI 연결도 통과했습니다. 새 PC의 SDK 미설치 상태에서 Philips가 동작한다는 의미는 아닙니다.

`tests/test_philips.py`는 실제 SDK 영역의 TIFF/ICC/CSV 출력, 배율 추정 방지, 표시 시작 좌표 기록, 원본 압축 유지 거부, 읽기 실패, 취소 시 미완성 파일 정리, 한글 경로, 브리지 프로세스 종료를 확인합니다. `tests/test_philips_gui.py`는 확장자 선택과 자동 압축 표시, 성공/실패가 섞인 CSV 작업을 검증합니다. 기존 standalone 11개, 압축 보존 6개, 피라미드 7개와 기존 GUI 옵션/원본 값 비저장 테스트도 통과했습니다. SDK 바이너리는 일반 배포본에 포함하지 않습니다. 설치와 출력 범위는 `docs/philips_support.md`를 참고하세요.

1.2.0은 Aperio 호환 설명으로 저장하여 별도의 OpenSlide 수정 없이 `openslide.objective-power`를 직접 제공합니다. 배율 숫자와 고정 호환 표기, 기술 JSON만 생성하며 원본 설명은 복사하지 않습니다. 합성 피라미드 테스트 7개에서 직접 배율 키, 등방성 MPP 키, 비등방성 MPP의 정확한 기술 정보 재읽기, 개인정보 표식 제거, 원본 압축·픽셀 보존, 마스크·취소를 검증했습니다. 비등방성 MPP는 OpenSlide 키를 생략하고 TIFF 표준 해상도 및 기술 JSON·CSV에 유지합니다. 1.1.2의 None 관찰 기록은 이전 출력에 해당합니다.

1.1.2는 출력 파일명 익명 변경 체크박스, 원본 이름 유지, 중복 이름 번호 처리를 추가했습니다. GUI·worker·독립 API·CLI에 연결했습니다. 기존 실제 출력의 OpenSlide 속성을 확인한 결과 `openslide.objective-power`는 None이고 `tiff.ImageDescription` JSON의 `objective_power`는 40.0입니다. 아래 실제 대용량 변환 기록은 1.1.1에서 수행했으며 이번 변경의 파일명·기존 파일 보호·CSV 연결은 합성 데이터로 검증했습니다.

1.1.1은 Magnification, Pixel Size, MPP, Physical Size를 TIFF 내부·CSV·정보 화면에 제공합니다. 배율은 원본 수치, 실제 크기는 전체 영상 픽셀 수와 MPP로 계산합니다. TIFF ImageDescription은 검증한 기술 수치만 새로 만든 JSON이며 원본 자유 텍스트는 제외합니다. 외부 뷰어의 배율 자동 표시는 뷰어별 지원에 따라 다릅니다.

기본 구조를 표준 피라미드 TIFF로 변경했습니다. 최대 해상도와 호환 원본 조직 축소 레벨의 JPEG 압축을 유지하고 필요한 작은 레벨만 추가 생성합니다. GUI에서 단일 해상도 TIFF도 선택할 수 있습니다. 모든 레벨에 개인정보 메타데이터 제거를 적용하며 영상에 직접 적힌 식별자는 사용자 검토 대상입니다.

## 검증

1.6.0: 전후 상태 코드와 3열 비교 표를 추가했습니다. 합성 원본의 설명·소프트웨어 값을 GUI에서 확인하고, 같은 표식이 반환 JSON·CSV·TIFF에 없는 것을 검증했습니다. 선택 행 상세 표시, 목록 비우기 시 메모리 해제도 확인했습니다. 이미지 `artifacts/ui_before_after_demo.png`는 개인정보가 아닌 합성 예시만 사용했습니다. 실제 원본 개인정보 값을 스크린샷이나 검증 로그로 저장하지 않았습니다.

1.5.0은 제거 내역 비교 및 전용 GUI 탭을 추가했습니다. 합성 원본의 설명·소프트웨어·일시·사설 태그·라벨·매크로·썸네일을 비교하고, ICC 포함/제외 및 원본에 없는 작성자 항목을 구분하는 테스트를 통과했습니다. 감사 내역에 개인정보 표식·원본 파일명이 누출되지 않고 CSV JSON과 API 내역이 일치함을 확인했습니다. CSV 전용은 제거 검증 내역을 생성하지 않습니다. 기존 standalone 11개·압축 보존 6개·피라미드 7개·ICC 2개·옵션 GUI도 통과했습니다.

기존 실제 SVS·NDPI 출력과 원본을 읽기 전용으로 비교한 내역은 `artifacts/removal_audit_validation.json`, 화면은 `artifacts/ui_removal_audit.png`입니다. 이번 실제 자료 검증에서 대용량 영상 재변환은 수행하지 않았습니다.

최종 1.5.0 EXE에서 제거 내역 반환, 원본 개인정보 표식 미포함, JPEG/Deflate·ICC·파일명 옵션과 취소를 검증했습니다. frozen GUI와 EXE 연결에서 '익명화 내역' 탭의 결과 표시도 확인했습니다.

1.4.0은 UI·브랜딩 변경입니다. 원본 로고·아이콘 PNG를 수정하지 않고 창과 EXE에 포함합니다. 설정·정보 탭, 작은 창의 설정 스크롤, 파일 목록, 옵션/설명 버튼, 기존 내보내기 연결을 검증했습니다. 화면 검증은 사용자 데스크톱 입력 없이 offscreen Qt 렌더링으로 수행했습니다. 변환 엔진은 1.3.0과 같으므로 대용량 재변환은 반복하지 않았습니다.

최종 EXE의 내장 logo/logo.png 및 logo/icon.png 바이트를 원본과 비교했고 Windows 아이콘 리소스도 확인했습니다. 실제 SVS·NDPI의 검사·썸네일 화면, 1240×900 및 1050×760 화면 배치를 확인했습니다. 최종 EXE 작업 테스트와 frozen GUI 연결도 통과했습니다. source-build.zip에는 두 원본 이미지가 포함됩니다.

실제 SVS·NDPI도 preserve_icc=True로 재변환했습니다. SVS의 원본 Vendor=aperio, ICC 13,113,264바이트가 TIFF 원본 태그와 일치했습니다. NDPI의 원본 Vendor=hamamatsu, ICC 없음도 확인했습니다. 두 결과 모두 OpenSlide 배율 40, 썸네일, 전체 타일 검증 및 원본 SHA-256 보존을 통과했습니다. 기록은 `artifacts/icc_vendor_validation.json`입니다. 최종 1.3.0 EXE에서 원본 ICC 바이트를 OpenSlide로 다시 읽는 테스트와 GUI 연결도 통과했습니다.

1.3.0: 원본 Vendor 재변환 보존과 임의 문자열 거부, JPEG/Deflate 각각의 ICC 포함·제외, 원본 프로파일 바이트와 OpenSlide 썸네일 ICC 일치, 원본 ICC가 없는 경우, ICC 별도 검토 상태·CSV를 테스트했습니다. 기존 standalone 11개, 압축 유지 6개, 피라미드 7개와 ICC 전용 2개가 검증 범위입니다. 원본 포함 ICC는 개인정보 제거 완료로 판정하지 않습니다.

1.2.0 실제 결과: `output/20260909_073622_242147/`. SVS·NDPI 모두 5개 레벨, 원본 압축 유지 및 원본 SHA-256 보존을 통과했습니다. 프로젝트 모듈을 가져오지 않는 별도 Python 프로세스에서 표준 OpenSlide만으로 두 파일의 `openslide.objective-power == '40'`, vendor=aperio, get_thumbnail을 확인했습니다. SVS의 MPP 키는 약 0.262583이고 NDPI의 서로 다른 X/Y MPP는 기술 JSON·TIFF 표준 해상도·CSV에 유지합니다. 최종 EXE에서도 표준 OpenSlide 배율 키와 파일명 옵션, GUI 연결을 검증했습니다.

1.1.1 실제 재변환 결과: `output/20260908_144503_980842/`. 두 파일 모두 40×이며 SVS는 110562×61468 px, MPP 0.262583/0.262583 µm/pixel, 실제 영역 29.031702×16.140452 mm입니다. NDPI는 126720×96768 px, MPP 0.229689689/0.229731903 µm/pixel, 실제 영역 29.106277×22.230697 mm입니다. TIFF JSON과 반환 기술 정보의 일치, CSV 실제 크기, 원본 SHA-256, 전체 타일·피라미드 검증을 통과했습니다. 최종 EXE 합성 테스트도 네 항목의 저장을 확인했습니다.

- 실제 SVS·NDPI를 각각 5개 레벨로 변환하고 원본 전체 SHA-256 보존, 전체 타일 무결성·디코딩, 최대 해상도 원본/출력 영역 픽셀 비교를 통과했습니다.
- 두 실제 출력 파일 모두 OpenSlide의 get_thumbnail이 축소 레벨을 사용했습니다. 최대 해상도 전체를 할당하지 않았습니다.
- 피라미드 전용 합성 테스트 6개 통과: 원본 두 레벨의 압축 데이터 일치, 작은 레벨 생성·미리보기, 개인정보 표식 제거, 마스크 전파, 취소·정리, 배율 재읽기와 원본 설명문 제외, 잘못된 배율 제외, 실제 크기 계산과 MPP 저장 해제.
- standalone 11개, 압축 유지 6개, 옵션 GUI 테스트 통과. 원본 이름 유지·중복 번호·기존 파일 및 원본 해시 보존·CSV 연결을 포함합니다.
- 최종 EXE를 Python/Conda/QT 환경 변수 없이 PATH=Windows System32인 별도 프로세스에서 실행했습니다. 파일 검사, 원본 2개 레벨 보존+추가 1개 레벨 생성, JPEG/Deflate, CSV 전용, 취소와 원본 보존 검증을 통과했습니다.
- GUI를 frozen 모드로 실행하여 실제 EXE 작업 프로세스에 연결했습니다. 작업 파일 전달, 진행률, TIFF/CSV 결과 수신, 임시 파일 정리를 검증했습니다. 사용자 데스크톱을 조작하는 자동화는 최종 검증에 사용하지 않았습니다.

실제 결과 크기와 미리보기 시간은 [피라미드 검증 기록](pyramid_tiff_validation.md)에 있습니다. SVS 약 1.07GB, NDPI 약 2.27GB이며 각각 원본 3개 레벨을 보존하고 작은 2개 레벨만 생성했습니다.

## 배포 환경

현재 Windows x64 PC의 yslee Python 3.12.12 / PyInstaller 6.17.0에서 빌드했습니다. OpenSlide Python 1.4.6, OpenSlide 라이브러리 4.0.1, PySide6 6.8.3을 포함합니다. 별도의 Python 미설치 가상머신이나 다른 Windows 버전에서는 검증하지 않았습니다. 디지털 서명과 인터넷 공개 게시는 수행하지 않았습니다.

기본 결과 폴더는 문서 폴더의 WSI Exports입니다. 원본 샘플은 번들에 포함하지 않습니다. ZIP에는 EXE, 사용 안내, 라이선스, 빌드 정보와 재빌드용 소스가 있습니다. 작업 임시 파일은 사용자 LocalAppData에 저장하고 완료 시 정리합니다.

yslee의 기존 qt.conf가 다른 Qt 플러그인을 가리키므로 빌드 시 같은 PySide6 휠의 플러그인을 묶습니다. Conda Python ctypes의 ffi.dll을 명시적으로 포함합니다. 콘솔 없는 EXE는 표준 입출력 대신 임시 JSON 파일로 작업을 전달합니다.

재현:

```shell
python -m pip install -r requirements-build.txt
python tools/build_release.py
python tests/test_release.py
python tests/test_release_gui.py
```

이전 단일 TIFF 릴리즈 기록은 `release_validation_1_0.md`입니다.
# 1.8.2 JPEG 2000 무손실 검증

- 합성 RGB 영상: 전체 픽셀이 TIFF 디코더와 OpenSlide 모두에서 원본과 일치. 모든 레벨의 압축 태그 33005, 개인정보 표식 제외, CSV 압축 기록 및 취소 정리 통과.
- 두 Philips 샘플: 중앙 768×640 영역의 SDK 표시 RGB와 출력 OpenSlide 픽셀 일치, ICC 보존 및 피라미드 검증 통과.
- 첫 Philips 샘플 전체 변환: 719,377,526바이트, 537.578초(약 8분 58초), 5개 레벨, 5,697개 타일 검증. `artifacts/philips_jpeg2000_validation.json`에 기록.
- 기존 측정은 Deflate 929,985,707바이트/156.094초, JPEG Q90 72,034,064바이트/108.985초. 이번 실행은 EXE 빌드 및 다른 검사와 일부 겹쳤으므로 동일 조건의 성능 비교는 아님. JPEG 2000의 속도 개선을 보장하지 않음.
- 새 EXE: JPEG 2000 전체 픽셀 일치와 ICC 읽기, 기존 압축 옵션, GUI 작업 처리, 동봉 Philips 런타임의 별도 Python/Conda 없는 PATH·홈 환경 검증 통과. 실제 새 Windows PC에서의 실행 시험은 수행하지 않음.
