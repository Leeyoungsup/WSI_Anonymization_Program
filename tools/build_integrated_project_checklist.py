"""Integrate reviewed Studio source workflows with the WSI checklist, without running the service."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_COMMIT = '8e3d0e849e4cb2a3e0ba9a2f3124674dcf3753f8'
REPO_URL = 'https://github.com/Leeyoungsup/Mediauto-studio_saas'

def studio_shot(filename, caption, width=6.3):
    picp = doc.add_paragraph()
    picp.paragraph_format.line_spacing = 1
    picp.paragraph_format.space_after = Pt(4)
    picp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    path = ROOT/'artifacts/mediauto_studio_review/figure/manual-redacted'/filename
    pic = picp.add_run().add_picture(str(path), width=Inches(width))
    pic._inline.docPr.set('descr', caption)
    p(caption, 'Small')

def ai_page(title, sub, items, shot=None, note=None):
    new(title, sub)
    if shot:
        studio_shot(*shot)
    rows(items)
    if note:
        p(note, 'Small')

def append_ai():
    ai_page('06. AI 운영환경 승인',
      '담당: 병원 전산·개인정보 담당 / 시점: 실데이터 최초 업로드 전 및 배포 변경 시', [
      ('06-1','병원 내부 서버 운영인지 외부 서버 이용인지 확정한다. 서버·DB·영상·캐시·백업의 위치, 관리 주체, 어반의 접근 방식과 필요한 처리위탁/제공 관계를 기록한다. 외부 서버는 별도 승인 전 업로드하지 않는다.','배포 위치·운영/접근 주체\nL1·L2·G1·G2 / P2'),
      ('06-2','승인된 HTTPS 주소, 서버·DB 접근권한, 저장장치·백업 암호화와 복구 절차를 실제 배포환경에서 확인한다. 계정 인증이나 TOTP 비밀키 암호화만으로 영상·DB 전체가 암호화되었다고 판단하지 않는다.','배포 점검표·복구 확인 기록\nL2·G2 → 운영안 / P2'),
      ('06-3','관리자는 외부 통신을 확인한다. 코드에는 공인 IP의 위치 조회와 PDF용 외부 라이브러리 로딩 경로가 있다. 폐쇄망이면 차단·내부 제공 등 승인된 구성을 검증하고, 외부 이용 시 대상·항목·국외이전 적용 여부를 검토한다.','외부 통신 허용/차단 기록\nL1·L2·G2 / P2'),
      ('06-4','같은 서버의 비참여 계정으로 프로젝트·슬라이드 조회 범위를 시험한다. 프로젝트 이름·Owner·역할 설정만으로 프로젝트 간 데이터 격리가 보장된다고 판단하지 않는다. 허용 범위를 넘으면 별도 인스턴스 등 승인된 분리 후 사용한다.','시험 계정·접근 범위·조치\nL2·G2 → 운영안 / P2'),
      ('06-5','승인된 시험 파일로 SVS·NDPI·TIFF와 필요한 Philips 파일을 열어본다. Philips는 서버의 SDK/브리지 및 사용권을 확인한다. 익명화 도구의 성공 여부와 AI 서버의 읽기·색상·MPP 호환성을 각각 확인한다.','형식별 시험·버전·확인자\nG2 → 운영안 / P1·P2'),
    ], note='확인 기준: Studio version.json 3.3.2 / 커밋 '+REPO_COMMIT[:12]+'. 코드·문서 검토 결과이며 병원 운영 서버의 설정·권한 시험을 대신하지 않습니다.')

    ai_page('07. 계정 승인과 권한 설정',
      '담당: 관리자 / 화면: Admin → Pending Approvals·Users / 완료 조건: 승인된 개인 계정만 사용', [
      ('07-1','Admin에서 사용자와 소속을 확인하고 승인한다. 공용 계정 대신 개인 계정을 사용하며 실제 업무에 맞게 Viewer·Labeler·Doctor·Admin 역할을 부여한다.','승인 사용자·역할·일자\nL2·G2 / P2'),
      ('07-2','Viewer의 AI 실행 제한, Labeler의 주석 작업 범위, Doctor/Admin의 검토·종결 권한을 실제 계정으로 확인한다. 기관 운영안에 따른 MFA·비밀번호·세션 정책을 적용한다.','역할별 기능 시험·인증 정책\nL2·G2 → 운영안 / P2'),
      ('07-3','참여 종료·업무 변경 시 계정을 비활성화하거나 역할을 회수한다. 원격 지원도 승인된 계정·기간으로 제한하고 로그를 확인한다. 작업 종료 시 Logout한다.','권한 부여·변경·회수 기록\nL2·G2 / P2'),
    ], ('11-admin/02-user-management.png','Admin → Users 예시 | 사용자 정보는 저장소에서 모자이크 처리한 화면입니다.'))

    ai_page('07. 프로젝트와 자동 분석 설정',
      '담당: Doctor/Admin / 화면: Project → New Project 또는 Info → Save', [
      ('07-4','승인된 과제로 프로젝트를 생성하고 Title·Hospital·Department·Owner를 확인한다. Description과 폴더 이름에는 환자명·등록번호 등 원본 식별자를 입력하지 않는다.','프로젝트명·담당자·승인 과제\nG1·G2 → 운영안 / P2'),
      ('07-5','Project default AI run list와 Cell Annotation AI assistance를 확인한다. 승인된 모델·조직·염색·해상도만 선택한다. 미확정 자동 분석은 꺼두고 Save 후 저장 상태를 확인한다.','모델/대상·자동 실행 설정\nG2·N1 → 운영안 / P2'),
      ('07-6','자동 분석은 업로드 후 유휴 시간에 실행될 수 있다. 프로젝트 설정과 Admin → Settings의 AI Worker 상태를 함께 확인한다. 설정 변경 시 적용 대상과 기존 결과 재검토 여부를 기록한다.','설정 변경 이력·확인자\nG2 → 운영안 / P2'),
    ], ('03-project/02-edit-project-settings.png','Project Information 예시 | 분석 항목 선택은 연구계획과 일치시킵니다.'))

    ai_page('08. 가명 케이스 코드로 연결 준비',
      '담당: 병원 데이터 관리 담당·검토자 / 시점: 익명화 검토 완료 후, Studio 업로드 전', [
      ('08-1','05단계까지 확인한 결과만 등록 대상으로 확정한다. 각 파일의 임의 이름 anonymous_…는 환자별 공통 코드가 아니다. Same Case 또는 Data Linkage를 쓸 경우 병원에서 별도 가명 케이스 규칙을 승인한다.','가명 코드 규칙·승인자\nG1·G2 → 운영안 / P1·P2'),
      ('08-2','원본→익명화 결과→등록용 파일명의 대응은 병원 내부에서만 관리한다. 필요하면 검토된 사본의 파일명을 가명 케이스 코드로 바꾸고 전달 목록·CSV 대응을 다시 확인한다. 원본 환자번호나 검체번호로 되돌리지 않는다.','대응표 보관 위치·최종 목록\nG1·G2 → 운영안'),
      ('08-3','Studio는 하이픈으로 나눈 파일명 일부를 케이스로 추출한다. 예: STUDY-A-000001-HE01.svs와 STUDY-A-000001-ER01.svs는 STUDY-A-000001로 묶인다. 이는 규칙 설명용 예시이며 코드 발급·대응표 생성 기능이 아니다.','시험 파일명·추출 케이스\nP2 / 연동 운영안'),
      ('08-4','같은 케이스는 함께 묶이고 다른 케이스는 섞이지 않는지 시험한다. 다른 프로젝트에서도 케이스 코드가 충돌하지 않도록 발급 범위를 정한다. 코드 충돌·오연결이 있으면 임상정보 입력과 분석을 보류한다.','동일/다른 케이스·프로젝트 시험\nG1·G2 → 운영안 / P2'),
    ], note='구현 근거: clinical_info.py는 파일명에서 case_name을 추출하고 케이스 공통 임상정보를 저장합니다. 프로젝트별 코드 격리를 전제로 삼지 않습니다. 연결이 필요 없는 과제는 08-2~08-4의 해당 없음 사유를 기록합니다.')

    ai_page('08. Slide Upload와 등록 확인',
      '담당: 업로드 권한 사용자 / 화면: Home → Upload → Project·Folder → browse files → Upload', [
      ('08-5','승인된 Project와 Folder를 먼저 선택한다. 검토 완료한 등록용 파일만 browse files 또는 드래그로 추가하고 Upload한다. 업로드는 익명화 처리 기능이 아니므로 원본을 넣지 않는다.','프로젝트·폴더·업로드 목록\nG1·G2 → 운영안 / P2'),
      ('08-6','동일 파일 처리에서 덮어쓰기 여부를 임의로 결정하지 않는다. 기존 주석·AI 결과 영향을 확인하고 승인된 경우만 적용한다. 실패 파일과 성공 파일을 구분해 요청 건수와 등록 건수를 대조한다.','성공 ____ / 실패 ____\n덮어쓰기 승인·재처리 기록\nG2 → 운영안 / P2'),
      ('08-7','등록 후 슬라이드를 열어 영상·MPP·색상·파일명을 확인한다. 관리자는 필요한 무결성 검증을 수행한다. 업로드 시 변환된 형식은 업로드 전 파일과 저장 파일의 해시가 같다고 가정하지 않는다.','등록 건수·열기·변환/해시 기록\nG2 → 운영안 / P2'),
    ], ('04-upload/01-slide-upload.png','Slide Upload 예시 | 파일 선택 전에 프로젝트와 폴더를 확인합니다.',2.6))

    ai_page('09. Data Linkage 임상정보 확인',
      '담당: 병원이 지정한 입력자·검토자 / 화면: Data Linkage → Project·Sample No → Search → Save', [
      ('09-1','가명 케이스를 검색하고 연결 슬라이드가 병원 대응표와 일치하는지 확인한다. Same Case의 연결 결과도 대조한다. 이름이 비슷하다는 이유로 같은 환자로 판단하지 않는다.','가명 케이스·연결 확인 기록\nG1·G2 → 운영안 / P2'),
      ('09-2','승인된 ER/PR·Ki67·PD-L1·HER2 등의 항목만 입력한다. 점수 칸에도 이름·등록번호·자유 서술 진료기록을 붙여넣지 않는다. 미상/해당 없음 표기는 기관 규칙에 맞춘다.','사용 항목·누락 처리 규칙\nG1·G2 → 운영안 / P2'),
      ('09-3','Save 후 다시 열어 값을 확인한다. 임상정보는 같은 케이스의 다른 슬라이드에도 공유될 수 있으므로 잘못 연결된 슬라이드가 없는지 재확인한다.','저장/재조회 결과·검토자\nG1·G2 → 운영안 / P2'),
      ('09-4','임상정보 결합으로 식별 위험이 커지는지 검토한다. 승인되지 않은 추가 변수·기관 간 결합은 보류한다. 임상정보 연동을 사용하지 않으면 해당 없음과 사유를 기록한다.','결합 항목·위험 검토·승인\nL1·G1·G2'),
    ], ('09-data-linkage/01-case-clinical-information.png','Data Linkage 예시 | 선택된 케이스와 오른쪽 Clinical Information을 함께 확인합니다.'))

    ai_page('10. AI 모델 선택과 분석',
      '담당: 승인된 AI 분석 사용자 / 화면: AI → 프로젝트·슬라이드 → Quanti 또는 VirtualStain', [
      ('10-1','슬라이드와 조직·염색을 확인하고 승인된 모델을 선택한다. Quanti HE, PD-L1, IHC의 분석 목적을 구분한다. PD-L1에서는 Stomach(CPS)/Lung(TPS)를 대상에 맞게 선택한다.','가명 슬라이드·모델·조직/염색\nG2·N1 → 운영안 / P2'),
      ('10-2','ROI 도구로 승인된 영역을 지정하거나 전체 슬라이드 분석 범위를 확인한 뒤 실행한다. 모델/가중치 식별정보·설정·ROI·일시를 기록한다. 화면에서 확인되지 않는 모델 버전은 관리자에게 확인한다.','모델 식별·ROI·실행 설정\nG2 → 운영안 / P2'),
      ('10-3','최종 완료·오류·취소 상태를 확인하고 표시된 세포·점수를 연구 검토자가 확인한다. 흐림·염색·스캐너 차이·부적절한 영역 등 품질 문제는 보완 또는 제외한다.','완료 상태·검토·제외 사유\nG2 → 운영안 / P2'),
      ('10-4','VirtualStain 등 합성 영상은 생성 결과임을 구분해 기록한다. AI 점수·가상 염색을 승인된 연구 범위를 넘어 확정 진단이나 실제 염색 결과로 취급하지 않는다.','결과 종류·사용 목적·검토자\n연구 운영안 / P2'),
    ], ('06-ai-analysis/15-quanti-pdl1-results.png','Quanti PD-L1 분석 예시 | 화면의 점수·연구 코드는 해당 캡처의 예시이며 성능 검증 근거가 아닙니다.'))

    ai_page('11. Tissue Annotation 작성·검토',
      '담당: 지정 주석 작성자·Doctor/Admin 검토자 / 화면: Annotation → Tissue Annotation', [
      ('11-1','프로젝트와 가명 슬라이드를 선택하고 승인된 클래스 정의로 조직 ROI를 작성한다. Slide Memo·Annotation Memo·클래스 이름에는 원본 식별자나 불필요한 임상기록을 입력하지 않는다.','클래스 정의·대상·작성자\nG1·G2 → 운영안 / P2'),
      ('11-2','Save 또는 Ctrl+S 후 다시 열어 주석·메모가 저장되었는지 확인한다. 원본 영상과 주석의 대응, 누락·잘못된 클래스를 검토한다.','저장/재조회·수정 기록\nG2 → 운영안 / P2'),
      ('11-3','Annotation → Review → Termination 상태를 기관 절차에 따라 처리한다. Labeler 작성과 Doctor/Admin 검토·종결을 구분한다. Termination은 작업 종결 상태이며 데이터 파기를 의미하지 않는다.','작성자·검토자·종결 일자\nG2 → 운영안 / P2'),
    ], ('07-tissue-annotation/01-annotation-viewer.png','Tissue Annotation 예시 | 우측 Annotation Status와 주석 저장 상태를 확인합니다.'))

    ai_page('11. Cell Annotation 패치 검토',
      '담당: 지정 주석 작성자·검토자 / 화면: Annotation → Cell Annotation → Patch View', [
      ('11-4','Required·Exclude 영역과 클래스 정의를 확인해 대상 패치를 정한다. 패치에도 조직 영상과 원본 유래 정보가 남을 수 있으므로 WSI와 같은 보관·반출 기준으로 관리한다.','대상 패치·클래스·제외 영역\nG1·G2 → 운영안 / P2'),
      ('11-5','AI assistance를 쓰면 승인된 모델인지 확인하고 자동 제안 셀을 검토·수정한다. 자동 생성된 셀을 검토 없이 정답 라벨로 확정하지 않는다.','보조 모델·검토·수정 기록\nG2 → 운영안 / P2'),
      ('11-6','각 패치의 Annotation·Review·Termination을 확인하고 누락·반려를 보완한다. Labeler는 허용된 작업 상태에서 편집하고, 검토·종결은 지정 권한자가 수행한다.','패치별 상태·검토/종결자\nG2 → 운영안 / P2'),
    ], ('08-cell-annotation/02-patch-list.png','Cell Annotation 예시 | Patch List의 단계별 상태를 확인하고 Patch View에서 검토합니다.'))

    ai_page('12. 결과 저장과 PDF 검토',
      '담당: Doctor/Admin 및 결과 검토자 / 화면: Save Results·Load Results → Visualize → PDF Export', [
      ('12-1','필요한 AI 결과 셀을 수정하고 Save Results로 사용자 저장본을 저장한다. Load Results로 원본 AI 결과와 사용자 편집본 중 무엇을 검토 중인지 확인하고 변경 사유를 남긴다.','결과 종류·편집자·수정 사유\nG2 → 운영안 / P2'),
      ('12-2','Visualize → PDF Export로 보고서를 저장한다. 기본 다운로드 폴더를 포함해 실제 저장 위치를 확인한다. PDF 제목·모델명·점수·대상 파일명이 검토한 결과와 일치하는지 확인한다.','PDF 경로·모델/결과 대조\nG2 → 운영안 / P2'),
      ('12-3','PDF·캡처·주석·패치의 파일명과 본문에 원본 식별자·사용자명·경로 등 불필요한 정보가 없는지 확인한다. 외부 공유는 14단계 승인 후 진행한다.','전달 후보 산출물·검토자\nG1·G2 → 운영안'),
      ('12-4','Clear Results는 화면 표시를 지우는 동작이며 원본 AI 캐시 파기가 아니다. 저장본 삭제만으로 원본 분석 결과·다운로드 PDF·백업까지 삭제되었다고 기록하지 않는다.','보관/파기 대상 구분\nL1·L2·G2 / P2'),
    ], ('06-ai-analysis/06-pdf-analysis-report.png','저장소의 PDF 예시 | 실제 보고서는 제목과 모델·점수 일치 여부를 별도로 검토합니다.'))

    ai_page('13. 작업 이력과 증빙 점검',
      '담당: 관리자·사업 담당 / 화면: Admin → Activity → 사용자 Details', [
      ('13-1','날짜·사용자로 조회해 Login·Slides·AI·Projects·Files 작업 이력을 확인한다. 이번 배치의 업로드·분석·권한 변경 기록과 체크리스트를 대조한다.','조회 기간·배치·점검 결과\nL2·G2·N1 / P2'),
      ('13-2','관리자는 감사 로그 수집·무결성 검증·접근권한·보존/백업을 점검한다. HMAC 체인 기능이 있다는 사실만으로 법정 기록항목·보존기간·변조 방지 요건을 모두 충족했다고 판단하지 않는다.','로그 점검·보존 정책·확인자\nL2·G2 / P2'),
      ('13-3','NIPA 중간·최종 점검에 사용할 설정·검증·교육·이슈 조치 증빙을 승인된 위치에 정리한다. 로그나 캡처를 제출할 때에도 사용자·환자 식별정보를 최소화한다.','증빙 목록·제출/검토 기록\nN1·G2'),
    ], ('11-admin/04-login-activity.png','Admin → Activity 예시 | 사용자·IP 등은 저장소에서 가린 화면입니다.'))

    ai_page('13. 학습·성능평가에 재사용하는 경우',
      '담당: 연구책임자·데이터 관리 담당 / 조건부: 별도 학습 또는 성능평가가 승인된 과제만 적용', [
      ('13-4','이번 과제가 기존 모델 분석만 수행하는지, 라벨 데이터 구축·성능평가·재학습까지 수행하는지 구분한다. 별도 학습을 하지 않으면 아래 해당 없음 사유를 기록한다.','□ 분석만 □ 평가 □ 학습\n승인 범위·계획서 / G1·G2·N1'),
      ('13-5','학습/평가용 WSI·패치·주석·임상정보의 추출 목록, 사용 모델, 데이터 버전을 고정한다. 동일 환자/케이스가 학습·검증·시험에 중복 배정되지 않도록 병원 가명 대응체계로 확인한다.','데이터 버전·분할·검토 기록\nG2·N1 → 연구 운영안'),
      ('13-6','별도 학습 서버·담당자·외부 라이브러리/클라우드·모델 반출 범위를 사전에 승인한다. 산출 모델·로그·중간 파일의 개인정보 잔존/재식별 위험과 보관·파기 계획도 검토한다.','학습 환경·산출물·이용/반출 승인\nL1·L2·G1·G2'),
      ('13-7','평가 목표·대상·제외 기준·지표를 사전에 정하고 검토 결과를 기록한다. 모델이나 설정을 변경하면 기존 결과와 구분하고 재검증 후 적용한다.','평가 계획·결과·변경 승인\nN1·G2 → 연구 운영안'),
    ], note='저장소에서 확인한 사용자 흐름은 기존 모델의 분석과 주석 작업입니다. AI 분석 버튼이 모델 재학습을 수행한다고 확인하지 않았으며, 이 페이지는 별도 연구계획이 있는 경우의 운영 절차입니다.')

def append_repo_sources():
    new('프로그램 근거와 운영 확인사항', '문서 작성 근거 / 실제 병원 서버의 검증 결과와 구분하여 사용')
    p('P1  WSI 익명화 프로그램 1.10.2', 'SourceHeading')
    p('현재 프로젝트 GUI·처리 경로·사용자 가이드 기준. WSI 화면은 data 샘플로 기존에 실행한 캡처이며 파일명·경로를 예시로 치환했습니다.', 'Small')
    p('P2  MeDIAuto Studio 3.3.2', 'SourceHeading')
    p('확인 커밋: '+REPO_COMMIT+' / 확인일: 2026.09.28. version.json과 현재 코드를 기준으로 했으며 과거 문서의 역할·버전 설명은 그대로 적용하지 않았습니다.', 'Small')
    link('저장소: MeDIAuto Studio SaaS', REPO_URL+'/tree/'+REPO_COMMIT)
    link('화면별 기능 안내: PAGE_FEATURE_GUIDE.md', REPO_URL+'/blob/'+REPO_COMMIT+'/docs/PAGE_FEATURE_GUIDE.md')
    link('실행 화면 출처: figure/manual-redacted', REPO_URL+'/tree/'+REPO_COMMIT+'/figure/manual-redacted')
    p('Studio 화면은 저장소의 기존 캡처이며 일부 버전 표시는 1.1.233입니다. 사용자·접속정보를 가린 사본을 사용했고 화면에 남은 연구 코드는 캡처 예시입니다. 이번 병원 배치의 처리 결과나 모델 성능 증빙이 아닙니다. 저장소가 비공개로 전환되면 P2 링크는 권한이 필요합니다.', 'Small')
    table(['확인한 구현','현장에서 확인할 사항'], [
      ('케이스 연동','파일명으로 케이스를 추출하고 공통 임상정보를 공유함. 가명 코드·프로젝트 간 충돌·오연결을 업로드 전에 시험.'),
      ('접근 통제','역할별 기능 제한은 있음. 프로젝트명·Owner가 프로젝트별 조회 권한을 보장하지 않으므로 실제 계정 시험 또는 승인된 환경 분리.'),
      ('외부 통신','geo.py의 공인 IP 위치 조회, visualization.js의 PDF 라이브러리 외부 로딩 경로 확인. 실제 배포 통신은 관리자가 점검.'),
      ('AI·저장·파기','기존 모델 추론·사용자 결과·조직/세포 주석 흐름 확인. 표시 지우기·작업 종결·저장본 삭제와 전체 데이터 파기를 구분.'),
    ], [2000,7360])
    p('프로그램 구현 근거는 config.py, models.py, routers/projects.py·slides.py, clinical_info.py, philips_proxy.py, AI/annotation 관련 경로와 화면별 가이드입니다. 저장소의 규제 충족 표현을 국가 인증·법적 적합성 판정으로 인용하지 않았습니다.', 'Small')
    p('본 작업에서는 코드를 읽고 제공된 화면을 확인했습니다. AI 서버를 새로 가동하거나 병원 데이터 업로드·분석·삭제를 수행하지 않았습니다.', 'Small')

source = (HERE/'build_program_checklist.py').read_text(encoding='utf-8')
source = source.replace('MeDIAuto_AI_Project_Privacy_Checklist_Draft_v05.docx', 'MeDIAuto_AI_Project_Privacy_Checklist_Integrated_v06.docx')
source = source.replace('v0.5', 'v0.6')
source = source.replace('프로젝트 범위 정리 초안', '익명화·AI 통합 과정별 검토안')
source = source.replace('문서 범위: 익명화 프로그램을 통한 WSI 가명처리와 MeDIAuto AI 프로젝트의 데이터 이용 과정. 현재 본문은 WSI 처리·검토·전달 절차이며, AI 데이터 준비·학습·검증·결과 활용 절차는 실제 프로젝트 흐름 확인 후 추가할 예정입니다.',
 '적용 범위: WSI 가명처리 → 병원 승인 환경의 Studio 등록 → 임상정보 연동·AI 분석·주석 → 결과 검토·공유·보관/파기. 익명화 도구 1.10.2와 Studio 3.3.2 기준이며, 수행하지 않는 기능은 사유를 적고 해당 없음으로 처리합니다.')
# Insert actual AI steps between anonymization acceptance and external release.
source = source.replace("new('06. 승인된 결과만 병원에서 전달'", "append_ai()\n\nnew('14. 승인된 자료·결과의 외부 전달'")
source = source.replace('담당: 병원 반출 승인자·작업자 / 수령: 승인된 어반 담당자 / 프로그램 밖에서 수행하는 단계',
 '조건부: 병원 밖으로 자료를 전달할 때 / 담당: 병원 승인자·작업자 / 수령기관·목적을 먼저 확정')
for i in range(1,6):
    source = source.replace("('06-"+str(i)+"'", "('14-"+str(i)+"'")
source = source.replace("new('07. 보관·종료 및 문제 발생 시 조치'", "new('15. 보관·종료 및 문제 발생 시 조치'")
for i in range(1,5):
    source = source.replace("('07-"+str(i)+"'", "('15-"+str(i)+"'")
source = source.replace('이번 결과 중 검토 완료된 영상과 검토된 CSV만 전달 폴더에 복사한다.',
 '승인된 영상·CSV·AI 보고서·주석·패치만 전달 폴더에 준비한다. 각 산출물의 식별 위험 검토를 확인한다.')
source = source.replace('05단계 보완이 끝난 경우에만 승인한다.', '해당 작업 단계의 보완이 끝난 경우에만 승인한다. 병원 내부 이용만 하면 반출 해당 없음으로 기록한다.')
source = source.replace('프로그램에는 전송·암호화·반출 승인 기능이 없다.', '프로그램의 결과 저장이 기관의 반출 승인을 대신하지 않는다.')
source = source.replace('최종 영상: ____건  CSV: ____개', '최종 영상: ____건  CSV/보고서/주석·패치: ____개')
source = source.replace('수령한 영상·CSV는 승인된 연구와 접근권한 범위에서만 사용한다.', '등록·수령한 영상·임상정보·AI 결과·주석·패치는 승인된 연구와 접근권한 범위에서만 사용한다.')
source = source.replace('이번 배치의 연구 사본·CSV·대응표·검증 기록별 보존기간과 파기일을 기록한다.', '영상·임상정보·AI 캐시·사용자 저장본·주석/패치·PDF·대응표·감사기록별 보존기간과 파기일을 정한다.')
source = source.replace('종료 시 승인된 방법으로 연구 사본·CSV·임시 파일·공유 사본을 파기하고 백업 처리 방안까지 확인한다.', '종료 시 서버 영상·DB·타일/AI 캐시·주석/패치·임시 파일·다운로드/공유 사본을 파기하고 백업 처리도 확인한다.')
source = source.replace('이 프로그램은 파일 처리 도구입니다. 계정 권한·보관 암호화·접속기록·전달·파기는 병원과 어반의 승인된 시스템 및 절차로 수행합니다.',
 'Studio의 Clear·Termination·슬라이드/프로젝트 삭제를 전체 파기 완료로 간주하지 않습니다. 관리자가 파기 대상을 대조하고 잔존 여부·백업·별도 임상정보·로그 보존을 확인합니다.')
source = source.replace('프로그램 01~07단계에 반영.', '익명화·등록·AI 이용·검토·안전한 관리 단계에 반영.')
source = source.replace("# Turn each source code", "append_repo_sources()\n\n# Turn each source code")
source = source.replace('source_urls = {code: url for code, title, body, url in refs}',
 'source_urls = {code: url for code, title, body, url in refs}\nsource_urls["P2"] = REPO_URL+"/blob/"+REPO_COMMIT+"/docs/PAGE_FEATURE_GUIDE.md"')
source = source.replace('(G1|G2|N1|L1|L2|L3)', '(G1|G2|N1|L1|L2|L3|P2)')
exec(compile(source, str(HERE/'build_program_checklist.py'), 'exec'))
