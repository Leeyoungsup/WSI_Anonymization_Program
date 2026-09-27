"""Build the Korean screenshot guide from capture_user_guide.py output."""
from pathlib import Path
import sys
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/pdf'
SHOTS = OUT/'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont('Korean','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('KoreanBold','C:/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFontFamily('Korean',normal='Korean',bold='KoreanBold')
PDF = OUT/'MeDIAuto_WSI_User_Guide_KO.pdf'
c = canvas.Canvas(str(PDF), pagesize=landscape(A4))
c.setTitle('MeDIAuto WSI 익명화 프로그램 사용자 가이드 - 1.10.1')
c.setAuthor('MeDIAuto / WSI Anonymization Program')
W,H = landscape(A4)
INK=HexColor('#17273D'); MUTED=HexColor('#607189'); PURPLE=HexColor('#6550D8')
styles={
 'body':ParagraphStyle('body',fontName='Korean',fontSize=11,leading=18,textColor=INK,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='Korean',fontSize=9,leading=14,textColor=MUTED,wordWrap='CJK'),
 'sub':ParagraphStyle('sub',fontName='KoreanBold',fontSize=14,leading=21,textColor=PURPLE,wordWrap='CJK'),
}
def text(s,x,y,width,style='body'):
    p=Paragraph(s,styles[style]); _,h=p.wrap(width,1000)
    if y-h < 42: raise ValueError('Content overflows: '+s[:50])
    p.drawOn(c,x,y-h)
    return y-h-12

def page(n,title,subtitle):
    c.setFillColor(HexColor('#F5F7FC')); c.rect(0,0,W,H,fill=1,stroke=0)
    c.setFillColor(PURPLE); c.rect(0,H-7,W,7,fill=1,stroke=0)
    c.setFont('KoreanBold',10); c.drawString(36,H-31,'MeDIAuto  /  WSI ANONYMIZATION')
    c.setFillColor(INK); c.setFont('KoreanBold',24); c.drawString(36,H-68,title)
    text(subtitle,36,H-82,W-72,'small')
    c.setStrokeColor(HexColor('#D8DFEC')); c.line(36,34,W-36,34)
    c.setFillColor(MUTED); c.setFont('Korean',8)
    c.drawString(36,20,'사용자 가이드 | 프로그램 1.10.1 | 2026.09.28 | 내부 연구용')
    c.drawRightString(W-36,20,f'{n:02d} / 10')

def shot(name,x,y,width,maxheight):
    path=SHOTS/(name+'.png')
    with Image.open(path) as im: iw,ih=im.size
    scale=min(width/iw,maxheight/ih); dw,dh=iw*scale,ih*scale
    c.setFillColor(white); c.roundRect(x-3,y-dh-3,dw+6,dh+6,5,fill=1,stroke=0)
    c.drawImage(str(path),x,y-dh,width=dw,height=dh)
    return y-dh

def section(title,body,y,x=36,width=360):
    y=text(title,x,y,width,'sub')
    return text(body,x,y,width)

page(1,'WSI 익명화 프로그램 사용자 가이드','실제 실행 화면으로 따라 하는 파일 추가부터 결과 확인까지')
y=470
y=section('이 문서의 대상','Windows에서 GUI로 병리 슬라이드를 검사하고, 원본 형식 또는 TIFF로 내보내는 사용자입니다.',y,width=290)
y=section('기본 작업 순서','실행 → 파일 추가 → 전체 검사 → 저장 방식 설정 → 내보내기 → 익명화 내역 확인',y,width=290)
y=section('실제 샘플로 확인','data 폴더의 SVS·NDPI·Philips 샘플을 검사하고 Philips 원본 형식 내보내기를 완료한 화면입니다.',y,width=290)
shot('01_start',356,468,450,318)
text('화면의 파일명은 Sample_번호로, 경로는 예시 경로로 치환했습니다. 캡처는 소스 GUI 실행 화면이며 EXE의 런타임 안내·샘플 버튼 표시는 다를 수 있습니다.',356,135,450,'small')
text('이 문서는 프로그램 사용 안내입니다. 영상 내부 식별자와 ICC 정보의 검토, 기관의 데이터 제공 절차는 별도로 확인해야 합니다.',36,105,290,'small')
c.showPage()

page(2,'01. 실행 및 화면 구성','배포본은 ZIP을 모두 풀고 WSI_Anonymization.exe를 실행합니다.')
shot('01_start',36,478,610,431)
y=478
y=section('배포본 준비','EXE 옆의 philips 폴더를 함께 유지하세요. 별도 Python·Conda 설치 없이 사용하는 구성입니다.',y,668,137)
y=section('왼쪽 목록','추가한 파일의 형식, 용량과 처리 상태를 표시합니다.',y,668,137)
y=section('오른쪽 탭','내보내기 설정 / 슬라이드 정보 / 익명화 내역을 전환합니다.',y,668,137)
y=section('하단 영역','출력 폴더, 영상 검토 확인, 전체 검사, 내보내기, 중지 버튼이 있습니다.',y,668,137)
c.showPage()

page(3,'02. 파일 추가와 처리 대상 확인','파일 추가 / 폴더 추가 / 드래그 앤 드롭으로 목록을 구성합니다.')
shot('02_files',36,478,610,431)
y=478
y=section('샘플 불러오기','소스 프로젝트의 data 폴더를 불러옵니다. 배포본에 data 폴더가 없으면 이 버튼은 숨겨집니다.',y,668,137)
y=section('목록 전체 처리','현재 버전은 “선택 항목 내보내기”를 눌러도 목록 전체를 처리합니다. 행 선택은 정보 확인용입니다.',y,668,137)
y=section('일부만 처리','목록 비우기를 누른 뒤 처리할 파일만 다시 추가하세요.',y,668,137)
y=section('지원 방식 확인','여러 형식이 섞이면 목록 전체에서 사용할 수 있는 저장 방식만 활성화됩니다.',y,668,137)
c.showPage()

page(4,'03. 전체 검사와 슬라이드 정보','내보내기 전에 파일을 읽을 수 있는지 먼저 확인합니다.')
y=475
y=section('1  전체 검사 실행','하단의 전체 검사를 누르면 목록을 순서대로 검사합니다. 완료 후 확인할 행과 슬라이드 정보 탭을 선택합니다.',y)
y=section('2  확인할 항목','조직 썸네일, 전체 픽셀 크기, 배율, MPP, 피라미드 레벨과 부속 이미지 목록을 확인합니다. 원본에 없는 기술 수치는 추정하지 않습니다.',y)
y=section('3  검사 결과의 의미','“읽기 검사 통과”는 구조 및 일부 영역을 읽었다는 뜻입니다. 환자정보가 모두 제거되었다는 판정은 아닙니다.',y)
y=section('미리보기가 없는 경우','대용량 단일 해상도 영상은 메모리 사용을 제한하기 위해 썸네일을 생략할 수 있습니다. 오류 메시지와 구분해서 확인하세요.',y)
shot('03_inspection',448,478,355,430)
c.showPage()

page(5,'04. 저장 방식 선택','목적과 입력 형식에 맞게 세 가지 방식 중 선택합니다.')
y=475
y=section('1  원본 형식 유지','호환 SVS는 .svs, NDPI는 .ndpi, Philips는 .isyntax로 저장합니다. 원본 조직 압축을 재사용하고 메타데이터를 새로 작성합니다.',y)
y=section('2  TIFF 변환 · 원본 압축 유지','호환 JPEG 구조의 SVS·NDPI·TIFF에서 사용할 수 있습니다. Philips의 고유 압축에는 사용할 수 없습니다.',y)
y=section('3  TIFF 변환 · 무손실 압축','읽은 RGB를 JPEG 2000 무손실 TIFF로 저장합니다. 원본 제조사 압축을 그대로 복사하는 방식과는 다릅니다.',y)
y=section('비활성화된 옵션','목록 중 지원하지 않는 입력이 있으면 비활성화됩니다. 저장 방식 옆 i 버튼에서 이유와 제한을 확인하세요.',y)
shot('04_settings',448,478,355,430)
c.showPage()

page(6,'05. 파일명·CSV·색상 설정','화면 예시는 원본 파일명 CSV 포함을 해제하고 ICC는 기본값인 유지로 설정했습니다.')
y=475
y=section('출력 파일명','“출력 파일명을 익명 이름으로 변경”을 켜면 anonymous_로 시작하는 이름을 사용합니다. 끄면 원본 이름이 결과에 남습니다.',y)
y=section('CSV의 원본 파일명','기본값은 포함입니다. 공유 목적이라면 “CSV에 원본 파일명 포함”을 해제할지 확인하세요. 영상 파일명 변경과 별개인 옵션입니다.',y)
y=section('원본 색상 프로파일 유지','세부 설정에서 확인합니다. ICC는 기본 보존이며 내부 설명 등은 별도 검토 대상입니다. 제외하면 뷰어 색상이 달라질 수 있어 목적에 맞게 결정합니다.',y)
y=section('출력 구조와 실제 크기','기본은 확대·축소 보기와 실제 크기 유지입니다. 원본 형식 유지에서는 구조·MPP 변경이 제한됩니다.',y)
shot('05_advanced',448,478,355,430)
c.showPage()

page(7,'06. 내보내기와 중지','출력 폴더를 지정하고 “선택 항목 내보내기”를 누릅니다. 현재는 목록 전체가 대상입니다.')
y=475
y=section('출력 위치','GUI에서는 원본 파일이 있는 폴더 또는 그 하위 폴더를 출력 위치로 지정할 수 없습니다. 별도 폴더를 선택하세요.',y,width=240)
y=section('처리 중','상태 문구와 진행률을 확인합니다. 파일 크기·저장 방식·디스크 속도에 따라 시간이 달라집니다.',y,width=240)
y=section('중지 요청','영상 저장은 취소 확인 지점에서 중단하고 미완성 파일을 정리합니다. 전체 검사는 현재 파일의 검사가 끝난 뒤 중지합니다.',y,width=240)
y=section('영상 검토 체크','목록의 모든 조직 영상을 직접 검토한 경우에만 체크합니다. 체크하지 않아도 내보낼 수 있으며 검토 필요로 기록됩니다.',y,width=240)
shot('06_running',310,470,495,350)
text('처리 중 창을 강제 종료하지 마세요. 정상 완료된 앞선 파일은 중지 후에도 유지됩니다. 진행률 100%만으로 판단하지 말고 최종 완료/실패 상태를 확인하세요.',310,99,495,'small')
c.showPage()

page(8,'07. 익명화 내역 확인','완료된 행을 선택하고 “익명화 내역” 탭을 확인합니다.')
y=475
y=section('전후 비교 읽기','항목 / 원본 / 익명화 결과 표에서 제거, 보존, 재작성, 별도 검토 상태를 확인합니다. 행을 선택하면 아래에 상세 내용이 나타납니다.',y)
y=section('비교 범위의 한계','“없음”은 해당 TIFF 태그 또는 부속 이미지 목록에 없다는 뜻입니다. 영상 전체나 모든 원본 필드에 식별자가 없다는 의미는 아닙니다.',y)
y=section('Philips 결과','원본 XML 값은 이 표에서 직접 비교하지 않습니다. 부속 이미지와 원본 블록 검증 등 Philips 경로의 범위에 맞게 결과를 읽으세요.',y)
y=section('원본 값 취급','화면에는 원본 메타데이터 값이 보일 수 있습니다. 문의용 스크린샷을 공유할 때 파일명과 원본 값이 노출되지 않게 주의하세요.',y)
shot('07_audit',448,478,355,430)
c.showPage()

page(9,'08. 결과 파일과 검증 상태','“결과 폴더 열기”로 이번 작업의 출력 위치를 확인합니다.')
y=475
y=section('저장되는 파일','선택한 출력 폴더 아래 실행 시각 폴더가 생성됩니다. 영상 저장과 CSV를 모두 선택하면 변환 영상과 metadata.csv가 저장됩니다.',y)
y=section('실제 캡처 결과','Philips 샘플을 원본 형식으로 내보냈습니다. 46,164개 압축 블록의 일치가 확인되었고 ICC는 보존되었습니다. 영상 내부 개인정보는 검토 필요 상태입니다.',y)
y=section('검증 범위','Philips·원본 NDPI는 전체 압축 데이터 검증과 일부 영상 영역 읽기를 수행합니다. 모든 영상 픽셀의 개인정보를 검사한 결과는 아닙니다.',y)
y=section('다른 프로그램에서 열기','TIFF 출력은 OpenSlide에서 읽을 수 있습니다. Philips .isyntax는 일반 OpenSlide로 열 수 없어 Philips 호환 도구가 필요합니다.',y)
shot('08_result',448,478,355,430)
c.showPage()

page(10,'09. 문제 해결과 전달 전 확인','프로그램의 기술 검증과 사용자의 영상 검토를 함께 확인하세요.')
y=475
y=section('Philips 파일을 열 수 없음','EXE 옆의 philips 폴더가 온전히 있는지 확인합니다. 소스 실행은 PHILIPS_PYTHON과 SDK 환경을 확인합니다.',y)
y=section('ICC 보존 오류','원본 ICC가 있지만 현재 읽기 경로에서 보존할 수 없는 경우입니다. ICC 제외의 색상 영향을 검토하고 허용할 때만 설정을 변경합니다.',y)
y=section('저장 실패 또는 CSV 잠금','저장 공간·권한·출력 경로를 확인합니다. Excel이 CSV를 잠그면 metadata_시각.csv로 저장될 수 있으므로 실제 결과 경로를 확인하세요.',y)
y=section('CSV만 저장한 경우','영상 변환과 익명화 제거 검증을 수행하지 않습니다. CSV 완료 상태를 영상 익명화 완료로 해석하지 마세요.',y)
y=475
y=section('전달 전 확인','1. 영상 파일명과 CSV에 원본 식별자가 남았는지<br/>2. 라벨·매크로와 처리 내역을 확인했는지<br/>3. 조직 영상 속 문자·식별자를 직접 검토했는지<br/>4. ICC 보존 여부와 검토 결과를 확인했는지<br/>5. 기관의 제공·반출 절차를 확인했는지',y,448,355)
y=section('추가 안내 문서','README.md: 설치와 함수 사용<br/>docs/storage_modes.md: 저장 방식<br/>docs/python_api_guide.md: API 전체 설명<br/>docs/native_philips.md: Philips 지원 범위',y,448,355)
text('제작 근거: 현재 1.10.1 소스 GUI와 data 샘플의 실제 실행 화면. 화면의 원본 식별자·경로는 예시로 치환했습니다. 이 가이드는 기관 승인 프로토콜이나 익명화 인증서가 아닙니다.',448,y,355,'small')
c.showPage()
c.save()
print(PDF)

# Render for visual QA; the isolated dependency folder avoids changing the app environment.
sys.path.insert(0,str(ROOT/'artifacts/guide_dependencies'))
import pymupdf
render=ROOT/'artifacts/user_guide_qa'
render.mkdir(parents=True,exist_ok=True)
doc=pymupdf.open(PDF)
for i,p in enumerate(doc):
    p.get_pixmap(matrix=pymupdf.Matrix(1.6,1.6)).save(str(render/f'page_{i+1:02d}.png'))
assert len(doc)==10
assert '사용자 가이드' in doc[0].get_text()
print('Rendered and text-checked',len(doc),'pages')
