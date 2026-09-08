# Windows EXE 1.0.0 검증

2026-09-08, 현재 Windows x64 PC의 yslee Python 3.12 환경에서 PyInstaller 6.17.0으로 빌드했습니다. 배포 형식은 콘솔 창이 없는 단일 EXE와 사용 안내·라이선스·재빌드용 소스를 담은 ZIP입니다. 인터넷 공개 게시 및 디지털 서명은 수행하지 않았습니다.

파일: `release/WSI_Anonymization-1.0.0-Windows-x64.zip`

배포본은 현재 단일 해상도 TIFF 설정을 유지합니다. 피라미드/내장 썸네일 옵션은 포함하지 않습니다. 기본 출력은 Windows 문서 폴더 아래 `WSI Exports`이며, 샘플 데이터는 번들에 포함하지 않습니다.

## 확인한 항목

- Python/Conda/QT 환경 변수를 제거하고 PATH를 Windows System32로 제한한 별도 프로세스에서 EXE 실행.
- EXE 작업 프로세스의 파일 검사, JPEG 압축 유지, 무손실 Deflate, CSV 전용 저장, 취소, 원본 보존 통과.
- 실제 EXE의 GUI 창 생성과 Qt 로딩 확인.
- GUI 코드를 frozen 모드로 실행하여 실제 EXE 작업 프로세스와 연결: 파일 기반 작업 전달, 진행률, TIFF/CSV 결과 수신, 임시 작업 파일 정리 통과. 데스크톱 입력에 의존하는 파일 선택 자동화는 검증 범위에 포함하지 않습니다.
- 기존 옵션 GUI 테스트 통과.
- 실제 SVS·NDPI 전체 파일을 EXE로 변환하고 압축 타일 무결성·전체 디코딩·OpenSlide 픽셀 비교 통과.

| 입력 | EXE 출력 바이트 | 변환·검증 시간 |
|---|---:|---:|
| SVS | 995,229,102 | 39.5초 |
| NDPI | 2,083,751,677 | 93.0초 |

실제 결과와 로그는 `artifacts/release_full_validation/`에 있으며 배포 ZIP에는 포함하지 않습니다. 첫 실행 압축 해제와 동시에 실행 중인 작업에 따라 시간은 달라집니다.

## 빌드 시 반영한 내용

yslee의 기존 qt.conf가 다른 Conda Qt의 플러그인을 가리키므로 PySide6 6.8.3 휠의 플러그인으로 교체해 묶습니다. Conda Python의 ctypes가 필요로 하는 ffi.dll을 명시적으로 포함합니다. 콘솔 없는 EXE의 표준 입출력에 의존하지 않도록 GUI와 작업 프로세스가 사용자 LocalAppData의 임시 JSON 파일로 통신합니다.

별도의 Python 미설치 가상머신이나 다른 Windows 버전에서의 검증은 수행하지 않았습니다. 실제 검증한 범위는 위와 같으며, 압축을 풀고 EXE를 실행하는 휴대용 배포본입니다.

재현 명령:

```powershell
python -m pip install -r requirements-build.txt
python tools/build_release.py
python tests/test_release.py
python tests/test_release_gui.py
```
