# Windows EXE 1.4.0 검증

배포 ZIP: `release/WSI_Anonymization-1.4.0-Windows-x64.zip`.

1.2.0은 Aperio 호환 설명으로 저장하여 별도의 OpenSlide 수정 없이 `openslide.objective-power`를 직접 제공합니다. 배율 숫자와 고정 호환 표기, 기술 JSON만 생성하며 원본 설명은 복사하지 않습니다. 합성 피라미드 테스트 7개에서 직접 배율 키, 등방성 MPP 키, 비등방성 MPP의 정확한 기술 정보 재읽기, 개인정보 표식 제거, 원본 압축·픽셀 보존, 마스크·취소를 검증했습니다. 비등방성 MPP는 OpenSlide 키를 생략하고 TIFF 표준 해상도 및 기술 JSON·CSV에 유지합니다. 1.1.2의 None 관찰 기록은 이전 출력에 해당합니다.

1.1.2는 출력 파일명 익명 변경 체크박스, 원본 이름 유지, 중복 이름 번호 처리를 추가했습니다. GUI·worker·독립 API·CLI에 연결했습니다. 기존 실제 출력의 OpenSlide 속성을 확인한 결과 `openslide.objective-power`는 None이고 `tiff.ImageDescription` JSON의 `objective_power`는 40.0입니다. 아래 실제 대용량 변환 기록은 1.1.1에서 수행했으며 이번 변경의 파일명·기존 파일 보호·CSV 연결은 합성 데이터로 검증했습니다.

1.1.1은 Magnification, Pixel Size, MPP, Physical Size를 TIFF 내부·CSV·정보 화면에 제공합니다. 배율은 원본 수치, 실제 크기는 전체 영상 픽셀 수와 MPP로 계산합니다. TIFF ImageDescription은 검증한 기술 수치만 새로 만든 JSON이며 원본 자유 텍스트는 제외합니다. 외부 뷰어의 배율 자동 표시는 뷰어별 지원에 따라 다릅니다.

기본 구조를 표준 피라미드 TIFF로 변경했습니다. 최대 해상도와 호환 원본 조직 축소 레벨의 JPEG 압축을 유지하고 필요한 작은 레벨만 추가 생성합니다. GUI에서 단일 해상도 TIFF도 선택할 수 있습니다. 모든 레벨에 개인정보 메타데이터 제거를 적용하며 영상에 직접 적힌 식별자는 사용자 검토 대상입니다.

## 검증

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
