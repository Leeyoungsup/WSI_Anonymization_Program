"""Capture actual Qt screens with display-only identifiers replaced for a guide."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import time
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QFontDatabase
from wsi_app.gui import Window, STYLE, configure_qt

OUT = ROOT / 'output/pdf/screenshots'
OUT.mkdir(parents=True, exist_ok=True)
configure_qt()
app = QApplication([])
for font in ('malgun.ttf', 'malgunbd.ttf', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
app.setFont(QFont('Malgun Gothic', 11))
w = Window()
w.resize(1360, 960)
w.show()

def capture(name, widget=None):
    previous = w.output.text()
    w.output.setText('D:/WSI_Exports')
    for row, path in enumerate(w.paths):
        w.table.item(row, 0).setText('Sample_%02d%s' % (row+1, path.suffix))
    app.processEvents()
    assert (widget or w).grab().save(str(OUT / (name + '.png')))
    w.output.setText(previous)
    print('Captured', name, flush=True)

def wait():
    deadline = time.monotonic() + 240
    while w.process is not None:
        app.processEvents()
        if time.monotonic() > deadline:
            w.cancel()
            raise TimeoutError('Guide capture worker timeout')
        time.sleep(.02)
    app.processEvents()

try:
    capture('01_start')
    sources = [next((ROOT/'data').glob('*.svs')), next((ROOT/'data').glob('*.ndpi')),
               min((ROOT/'data').glob('*.i2syntax'), key=lambda p:p.stat().st_size)]
    w.add_paths(sources)
    w.include_filename.setChecked(False)
    capture('02_files')
    w.start('inspect')
    wait()
    assert w.failed == 0, 'Sample inspection failed'
    w.table.selectRow(0)
    w.side_tabs.setCurrentIndex(1)
    capture('03_inspection', w.side_tabs)
    w.side_tabs.setCurrentIndex(0)
    capture('04_settings', w.side_tabs)
    w.advanced_toggle.setChecked(True)
    capture('05_advanced', w.side_tabs)
    # Export one actual Philips sample to keep the example small and reproducible.
    w.clear()
    w.add_paths([sources[2]])
    w.include_filename.setChecked(False)
    w.preserve_icc.setChecked(True)
    w.output.setText(str(ROOT/'artifacts/user_guide_export'))
    w.start('copy')
    for _ in range(15):
        app.processEvents()
        time.sleep(.02)
    capture('06_running')
    wait()
    assert w.failed == 0, 'Philips export failed'
    report = w.results[0]['report']
    # Source values shown by the audit are UI-only. Replace those before capture.
    w.source_display_values[0] = {'filename':'Sample_01.i2syntax', 'csv_filename':'Sample_01.i2syntax',
        '_notice':'Philips 원본 XML 값은 이 표에서 비교하지 않습니다.'}
    w.show_selection()
    w.side_tabs.setCurrentIndex(2)
    capture('07_audit', w.side_tabs)
    w.side_tabs.setCurrentIndex(1)
    w.details.setPlainText(w.details.toPlainText().replace(str(w.results[0]['directory']),
                         'D:/WSI_Exports/<실행 시각>'))
    w.details.verticalScrollBar().setValue(0)
    capture('08_result', w.side_tabs)
    w.side_tabs.setCurrentIndex(2)
    capture('09_complete')
    summary = {key:report.get(key) for key in ('format','compression','verified_tiles',
        'icc_profile_copied','status','all_compressed_blocks_verified')}
    (OUT/'capture_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary), flush=True)
finally:
    w.close()
