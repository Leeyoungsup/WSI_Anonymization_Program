# WSI Anonymization Program

Windows에서 SVS·NDPI를 검사하고 **검토용 비식별 사본**을 생성하는 데스크톱 프로그램입니다. 현재 버전은 완전 익명화 인증을 제공하지 않으며, 모든 사본에 `검토 필요` 상태를 표시합니다.

## 실행

프로젝트 폴더의 **`Launch_WSI.vbs`를 더블클릭**하세요. 이 PC의 `%USERPROFILE%\.conda\envs\yslee\pythonw.exe`를 사용해 콘솔 없이 창을 엽니다.

터미널에서는 다음과 같이 실행할 수 있습니다.

```powershell
conda run --no-capture-output -n yslee python app.py
```

다른 PC에서는 먼저 Python 환경과 의존성이 필요합니다. 독립 실행 EXE 배포본은 아직 포함하지 않았습니다.

```powershell
conda run -n yslee python -m pip install -r requirements.txt
```

## 사용 순서

1. `샘플 불러오기` 또는 `파일 추가`로 SVS·NDPI 파일을 추가합니다. 끌어다 놓기도 지원합니다.
2. `전체 검사`를 누르면 읽기 상태, 조직 썸네일, 메타데이터 항목을 확인할 수 있습니다.
3. 원본 폴더 밖의 출력 폴더를 선택합니다. 기본값은 프로젝트의 `output/`입니다.
4. `검토용 사본 만들기`를 누르면 원본을 보존하며 처리하고 조직 압축 데이터와 영상 재열기를 검증합니다.
5. `결과 폴더 열기`로 무작위 ID 폴더 내 WSI 사본과 `report.json`을 확인합니다.

중지는 현재 파일이 완료된 뒤 적용됩니다. 처리 중 창 닫기도 중지를 요청하며, 현재 파일 완료 후 다시 닫을 수 있습니다.

## 현재 지원 범위

- SVS: 라벨·매크로 제외, 메타데이터 정리, 조직 타일과 썸네일 보존.
- NDPI: 4GB 미만이고 라벨·매크로/다중 초점면이 없는 구조에서 ASCII 필드 제거. 전용 비문자 태그·영역 지도·미참조 영역은 남으므로 추가 검토가 필요합니다.
- 원본과 출력의 조직 압축 데이터 전체 해시 비교, 피라미드 비교, 영역 읽기 검사.
- 검사·처리는 별도 프로세스에서 실행합니다. 원본과 결과 파일을 외부 서비스로 전송하지 않습니다.

자세한 제한은 [처리 정책](docs/processing_policy.md), 최초 샘플 구조는 [샘플 검사 기록](docs/sample_inspection.md)을 참고하세요.

## 검증

로컬 `data/`의 샘플 2개로 GUI 검사·사본 생성·오류 복구·중지 및 원본 전체 SHA-256 보존을 확인합니다. 테스트 사본은 임시 폴더에 생성 후 정리합니다.

```powershell
conda run --no-capture-output -n yslee python tests/smoke_gui.py
```

읽기 전용 구조 검사 도구도 사용할 수 있습니다.

```powershell
conda run -n yslee python tools/inspect_samples.py data
```
