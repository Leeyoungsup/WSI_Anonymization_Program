"""Preserve focused scope while restoring per-item source mapping tables."""
from pathlib import Path

source=Path(__file__).with_name('build_pdl1_focused_checklist.py').read_text(encoding='utf-8')
replacement='''
pending=[]
mapping={
'01':('연구·처리 근거',['L1','L3','G1']),
'02':('망 접근 통제',['L2'],'운영안'),
'03':('권한·저장 보호',['L2','G2']),
'04':('안전한 이용 환경',['L2','G2'],'운영안'),
'05':('식별 위험 검토',['G1','G2']),
'06':('식별정보 처리',['G1','G2'],'운영안'),
'07':('처리 품질·적정성',['G1','G2'],'운영안'),
'08':('적정성 검토',['G1','G2']),
'09':('접근권한 확인',['L2'],'운영안'),
'10':('검토된 자료 이용',['G1','G2'],'운영안'),
'11':('등록 자료 대조',['G2'],'운영안'),
'12':('영상·식별 위험 확인',['G1','G2'],'운영안'),
'13':('승인 목적 내 분석',['G2'],'연구 운영안'),
'14':('결과 상태 확인',['G2'],'연구 운영안'),
'15':('분석 결과 검토',['G2'],'연구 운영안'),
'16':('목적·결과 관리',['L1','G2'],'연구 운영안'),
'17':('안전한 보관',['L1','L2','G2']),
'18':('제공·접근 승인',['L1','L2','G1']),
'19':('사고 조치·보고',['L1','G2','N1']),
'20':('파기·권한 회수',['L1','L2','G2']),
'21':('사업자료 대조',['N1']),
}
names={'L1':'개인정보보호법','L2':'안전성 확보조치','L3':'생명윤리법',
       'G1':'보건의료 지침','G2':'가명정보 지침','N1':'NIPA 공모자료'}
def inline_link(para,code):
    h=OxmlElement('w:hyperlink');h.set(qn('r:id'),para.part.relate_to(urls[code],RT.HYPERLINK,is_external=True))
    r=OxmlElement('w:r');rp=OxmlElement('w:rPr')
    color=OxmlElement('w:color');color.set(qn('w:val'),'2E74B5');rp.append(color)
    u=OxmlElement('w:u');u.set(qn('w:val'),'single');rp.append(u);r.append(rp)
    tx=OxmlElement('w:t');tx.text=code+' '+names[code];r.append(tx);h.append(r);para._p.append(h)
def flush():
    if not pending:return
    t=table(['확인 항목','수행 방법·확인 기준','관련 기준 · 링크','결과'],
      [(code+'\\n'+title,body,'','□ 완료\\n□ 보완\\n□ N/A') for code,title,body in pending],
      [1300,4760,2400,900])
    for row,(code,title,body) in zip(t.rows[1:],pending):
        para=row.cells[2].paragraphs[0]
        context,codes,*kind=mapping[code]
        para.add_run(context+'\\n').bold=True
        for i,c in enumerate(codes):
            if i:para.add_run('\\n')
            inline_link(para,c)
        if kind:para.add_run('\\n※ '+kind[0])
    pending.clear()
def action(code,title,body):
    pending.append((code,title,body))
'''
start=source.index('def action(')
end=source.index('def record(',start)
source=source[:start]+replacement+'\n'+source[end:]
source=source.replace("def record(text=''):\n", "def record(text=''):\n    flush()\n")
source=source.replace("heading('배치별 확인 기록')", "flush()\nheading('배치별 확인 기록')")
source=source.replace("heading('배치별 확인 기록')", "heading('배치별 확인 기록')\n_record_start=len(doc.paragraphs)")
source=source.replace("new('06  공식 참고자료와 적용 범위'", "for _p in doc.paragraphs[_record_start:]:\n    _p.style='Small'\n\nnew('06  공식 참고자료와 적용 범위'")
source=source.replace('MeDIAuto_PDL1_Privacy_Checklist_v08.docx','MeDIAuto_PDL1_Privacy_Checklist_Linked_v09.docx').replace('v0.8','v0.9')
source=source.replace("'교수님 PC에서 익명화·검토\\n↓ 직접 연결로 처리본 업로드\\n병원망에 연결하지 않은 로컬 서버에서 열람·PD-L1 분석\\n↓ 교수님 PC에서 AI 결과 확인·보관'", "'교수님 PC: 익명화·검토 → 직접 연결로 처리본 업로드\\n로컬 서버(병원망 미연결): 뷰어·PD-L1 분석 → 교수님 PC에서 결과 확인'")
source=source.replace("',5.6)","',5.0)")
source=source.replace('사용법: 확인을 마친 항목에만 체크합니다. 보완 사항은 5쪽에 기록하고 해결 전 해당 자료의 다음 단계 진행을 보류합니다. 근거 문서는 6쪽에서 확인할 수 있습니다.',
 '사용법: 항목별 결과를 표시하고 보완·N/A 사유는 5쪽에 기록합니다. 파란 기준명을 클릭하면 공식 원문이 열립니다. ※ 운영안은 해당 기준을 본 작업에 적용한 절차이며, 지침이 특정 버튼·AI 검증법을 지정했다는 뜻은 아닙니다.')
exec(compile(source,str(Path(__file__).with_name('build_pdl1_focused_checklist.py')),'exec'))
