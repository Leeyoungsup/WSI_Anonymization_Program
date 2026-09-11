MeDIAuto Anonymization 1.10.0 — Windows x64 · 내부 연구용

ZIP 전체를 풀고 WSI_Anonymization.exe를 실행하세요. 옆의 philips 폴더도 함께 유지하세요.
Python/Conda/SDK를 따로 설치할 필요가 없습니다.

저장 방식
- 1. 원본 형식 유지: 호환 SVS는 .svs, NDPI는 .ndpi, Philips는 .isyntax로 저장합니다. 원본 조직 압축과 단계를 유지합니다.
- 2. TIFF 변환 · 원본 압축 유지: 호환 JPEG 구조의 SVS·NDPI·TIFF를 재사용합니다. Philips는 지원하지 않습니다.
- 3. TIFF 변환 · 무손실 압축: 모든 입력을 JPEG 2000 무손실 TIFF로 저장합니다. 용량과 시간이 늘어날 수 있습니다.
목록 전체에서 지원하지 않는 방식은 비활성화하며 ⓘ에서 이유를 확인합니다.
호환 SVS·NDPI·Philips를 함께 추가해 1번으로 처리할 수 있습니다. 일반 TIFF 등 지원하지 않는 입력이 섞이면 가능한 방식으로 변경됩니다.
자세한 지원 범위는 STORAGE_MODES.md와 NATIVE_SVS_NDPI.md를 참고하세요.
출력 구조·실제 크기 정보·색상 프로파일은 세부 설정에 있습니다.

Philips 원본 유지 결과는 일반 OpenSlide에서 열리지 않습니다. 이 프로그램이나 Philips 호환 도구로 읽으세요.
원본 조직 압축 블록은 그대로 보존하되 XML과 개인정보 메타데이터·라벨·매크로는 새 파일에 복사하지 않습니다.
색상 프로파일은 기본 제외이며 제외 시 표시 색상이 달라질 수 있습니다. 유지 시 프로파일 내부 정보도 검토해야 합니다.
영상 속 이름이나 식별자는 직접 확인해야 합니다. 전체 압축 블록을 비교하고 일부 영상 영역을 읽어 검증합니다.
결과와 CSV는 날짜·시간 폴더에 저장합니다. 자세한 안내는 NATIVE_PHILIPS.md를 참고하세요.

아래는 기존 TIFF 기능에 관한 1.8.2 당시 참고 설명입니다. 현재 GUI는 위의 세 가지 방식과 지원 범위를 적용합니다.

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

MeDIAuto Anonymization 1.8.2 — Windows x64 · 동일 기관 내부 연구용

GUI: Philips 지원·SDK 동봉 안내를 상단에 표시합니다. 압축 선택란 아래에서 파일 형식별 처리 방식과 JPEG 손실 여부를 확인하세요.

Philips SDK와 독립 Python 3.7 런타임을 동봉했습니다. 다른 연구용 PC에서 Python/Conda/SDK 설치 없이 실행합니다.
ZIP을 모두 풀고 WSI_Anonymization.exe를 실행하세요. 옆의 philips 폴더를 함께 유지하세요.
philips/SDK.zip은 보관용 SDK 원본입니다. 실행을 위해 다시 풀 필요가 없습니다. 자세한 안내: PHILIPS.md.
Philips 압축 선택: 무손실 Deflate 또는 JPEG Q90 (추가 손실 있음).
'형식별 자동 · Philips JPEG Q90 (손실)'를 선택하면 Philips만 JPEG로 재압축합니다.
Philips iSyntax 고유 압축을 TIFF에 그대로 유지하는 기능은 아닙니다. 첫 샘플: 원본 105MB → JPEG TIFF 약 72MB.

익명화 내역을 항목/원본/익명화 결과 표로 비교합니다. 행을 선택하면 아래에 상세 값을 표시합니다.
원본 TIFF 설명문·날짜·소프트웨어 값은 화면 메모리에만 두고 CSV/반환 JSON에 저장하지 않습니다.
원본 값 읽기는 최대 64 IFD, 태그당 4 KiB입니다. 초과 내용은 생략 표시합니다.
기존 CSV 원본 파일명 포함, ICC 보존 옵션은 이 화면 표시와 독립적입니다.

내보내기 완료 후 '익명화 내역' 탭에서 제거·보존·원본에 없음·검토 필요를 확인합니다.
원본/출력 TIFF 태그와 원본 부속 이미지 존재 여부를 비교합니다. 원본 텍스트 값은 화면에서만 확인합니다.
CSV의 anonymization_audit 열에도 내역을 저장합니다. CSV 전용 작업은 제거 검증을 하지 않습니다.
JPEG 부가정보는 제외 정책 적용으로 표시하며 원본 존재 여부는 별도로 집계하지 않습니다.
이 내역은 환자정보의 존재 여부를 자동 탐지하거나 완전한 익명화를 인증한 결과가 아닙니다.

MeDIAuto 로고와 아이콘 적용, 파일 목록/내보내기 설정/슬라이드 정보 화면을 정리했습니다.
오른쪽 탭에서 설정과 정보를 전환합니다. 검사·내보내기를 시작하면 정보 탭으로 이동합니다.
작은 창에서는 설정 영역을 스크롤할 수 있습니다. 로고와 아이콘은 EXE에 포함됩니다.

원본 Vendor를 정보 화면·TIFF 기술 정보·CSV에 표시합니다.
출력 openslide.vendor=aperio와 원본 Vendor(예: hamamatsu)는 구분합니다.
원본 ICC 포함 체크박스를 추가했습니다. 기본 제외이며 원본에 ICC가 없으면 생략합니다.
ICC 포함 시 색상 프로파일과 그 안의 부가정보가 그대로 복사되므로 별도 검토가 필요합니다.
이 경우 metadata_clean=False 및 ICC 검토 필요 상태로 기록합니다.
OpenSlide의 color_profile로 읽을 수 있습니다. ICC 포함 옵션 자체는 색상 변환을 수행하지 않습니다.

출력 파일명을 익명 이름으로 변경: 기본 체크. 해제하면 원본 이름 + .tiff로 저장합니다.
같은 이름이 있으면 _2, _3 등을 붙이고 기존 파일은 덮어쓰지 않습니다.
원본 이름에 개인정보가 있으면 해제 시 결과 파일명에도 남습니다.
CSV 원본 파일명 포함 옵션과는 독립적이며 i 버튼에서 설명을 볼 수 있습니다.
새 출력은 Aperio 호환 TIFF이며 openslide.objective-power로 배율을 직접 읽습니다.
원본에 배율이 없으면 키를 생략합니다. 이전 출력 파일은 재변환해야 합니다.
OpenSlide vendor=aperio는 출력 호환 형식이며 원본 스캐너를 나타내지 않습니다.
X/Y MPP가 같은 경우 OpenSlide MPP 키도 제공합니다. 다른 경우 두 키를 생략하고
정확한 X/Y를 TIFF 표준 해상도 태그, 기술 JSON 및 CSV에 유지합니다.

원본의 대물렌즈 배율은 숫자만 TIFF ImageDescription에 새로 기록합니다.
Pixel Size는 전체 영상 픽셀 수, Physical Size는 픽셀 수 × MPP / 1000(mm)입니다.
이 네 가지 기술 정보를 TIFF, CSV, 프로그램 정보 화면에서 확인할 수 있습니다.
MPP는 기존처럼 TIFF 해상도 태그와 CSV에 저장합니다. 배율은 CSV에도 저장합니다.
배율이 없는 입력은 추정하지 않습니다. 이 프로그램에서는 확인할 수 있지만,
외부 뷰어의 배율 표시는 해당 뷰어의 기술 메타데이터 지원에 따라 다릅니다.

실행
1. ZIP 압축을 해제합니다.
2. WSI_Anonymization.exe를 더블클릭합니다. Python/Conda 설치는 필요하지 않습니다.
3. 파일 추가 또는 드래그로 SVS/NDPI 파일을 넣습니다.
4. 내보내기 옵션과 출력 폴더를 선택하고 '선택 항목 내보내기'를 누릅니다.
   각 옵션 옆 i 버튼에서 설명을 볼 수 있습니다.

기본 출력: 문서 폴더의 WSI Exports / 날짜·시간 폴더
기본 압축: 원본 JPEG 유지. 지원하지 않는 압축 구조는 자동 재압축하지 않습니다.
기본 구조: 표준 피라미드 TIFF. OpenSlide의 get_thumbnail()을 사용할 수 있습니다.
최대 해상도와 호환 원본 축소 레벨의 JPEG 압축은 유지하고, 작은 추가 레벨만 생성합니다.
출력 구조에서 이전 단일 해상도 TIFF를 선택할 수도 있습니다.
CSV에는 선택한 경우 원본 파일명이 포함됩니다.
영상 속에 직접 찍힌 개인정보는 사용자 검토가 필요합니다.

설치형 프로그램이 아닌 휴대용 EXE입니다. 첫 실행은 내장 라이브러리를 임시 폴더에
풀기 때문에 잠시 걸릴 수 있습니다. 인터넷 연결 없이 변환할 수 있습니다.
디지털 서명은 적용하지 않았습니다. 게시자의 서명 인증서를 포함하지 않습니다.
동봉된 라이선스 안내와 source-build.zip은 배포 시 함께 전달하세요.

지원 대상: Windows 10/11 x64. 실제 검증한 PC/환경과 검증 범위는 릴리즈 기록을 참조하세요.
별도 OS 가상머신 검증이나 코드 서명은 이 배포본에 포함되지 않습니다.

소스에서 재빌드
64비트 Python 3.12 환경에서:
  python -m pip install -r requirements-build.txt
  python tools/build_release.py
빌드 도구가 release/ 아래 EXE, ZIP, 체크섬을 생성합니다.
