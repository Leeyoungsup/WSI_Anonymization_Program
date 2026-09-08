# Windows EXE 1.1.1 검증

배포 ZIP: `release/WSI_Anonymization-1.1.1-Windows-x64.zip`.

1.1.1은 Magnification, Pixel Size, MPP, Physical Size를 TIFF 내부·CSV·정보 화면에 제공합니다. 배율은 원본 수치, 실제 크기는 전체 영상 픽셀 수와 MPP로 계산합니다. TIFF ImageDescription은 검증한 기술 수치만 새로 만든 JSON이며 원본 자유 텍스트는 제외합니다. 외부 뷰어의 배율 자동 표시는 뷰어별 지원에 따라 다릅니다.

기본 구조를 표준 피라미드 TIFF로 변경했습니다. 최대 해상도와 호환 원본 조직 축소 레벨의 JPEG 압축을 유지하고 필요한 작은 레벨만 추가 생성합니다. GUI에서 단일 해상도 TIFF도 선택할 수 있습니다. 모든 레벨에 개인정보 메타데이터 제거를 적용하며 영상에 직접 적힌 식별자는 사용자 검토 대상입니다.

## 검증

1.1.1 실제 재변환 결과: `output/20260908_144503_980842/`. 두 파일 모두 40×이며 SVS는 110562×61468 px, MPP 0.262583/0.262583 µm/pixel, 실제 영역 29.031702×16.140452 mm입니다. NDPI는 126720×96768 px, MPP 0.229689689/0.229731903 µm/pixel, 실제 영역 29.106277×22.230697 mm입니다. TIFF JSON과 반환 기술 정보의 일치, CSV 실제 크기, 원본 SHA-256, 전체 타일·피라미드 검증을 통과했습니다. 최종 EXE 합성 테스트도 네 항목의 저장을 확인했습니다.

- 실제 SVS·NDPI를 각각 5개 레벨로 변환하고 원본 전체 SHA-256 보존, 전체 타일 무결성·디코딩, 최대 해상도 원본/출력 영역 픽셀 비교를 통과했습니다.
- 두 실제 출력 파일 모두 OpenSlide의 get_thumbnail이 축소 레벨을 사용했습니다. 최대 해상도 전체를 할당하지 않았습니다.
- 피라미드 전용 합성 테스트 6개 통과: 원본 두 레벨의 압축 데이터 일치, 작은 레벨 생성·미리보기, 개인정보 표식 제거, 마스크 전파, 취소·정리, 배율 재읽기와 원본 설명문 제외, 잘못된 배율 제외, 실제 크기 계산과 MPP 저장 해제.
- 기존 standalone 10개, 압축 유지 6개, 옵션 GUI 테스트 통과.
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
