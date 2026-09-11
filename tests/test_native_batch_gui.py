"""Real mixed SVS/NDPI/Philips batch, optionally routed through the packaged EXE."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile
import time
import hashlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from wsi_app.gui import Window, configure_qt, ROOT
import wsi_app.gui as gui
if '--frozen' in sys.argv:
    gui.FROZEN = True
    gui.ROOT = ROOT/'dist'
    sys.executable = str(gui.ROOT/'WSI_Anonymization.exe')
configure_qt()
app = QApplication([])
w = Window()
sources = [next((ROOT/'data').glob('*.svs')), next((ROOT/'data').glob('*.ndpi')),
           ROOT/'data/20260511_124345.i2syntax']
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
before = [digest(path) for path in sources]
with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as folder:
    w.add_paths(sources)
    assert w.storage_choice.currentData() == 'native'
    assert [w.storage_choice.model().item(i).isEnabled() for i in range(3)] == [True, False, True]
    w.output.setText(folder)
    w.include_filename.setChecked(False)
    w.preserve_icc.setChecked(True)
    assert not w.structure.isEnabled() and not w.preserve_mpp.isEnabled()
    w.start('copy')
    deadline = time.monotonic() + 180
    while w.process is not None:
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(.01)
    assert w.completed == 3 and w.failed == 0, {i: r.get('error') for i,r in w.results.items()}
    formats = ['aperio-svs','hamamatsu-ndpi','philips-isyntax']
    suffixes = ['.svs','.ndpi','.isyntax']
    for row, (expected, suffix) in enumerate(zip(formats, suffixes)):
        report = w.results[row]['report']
        assert report['format'] == expected
        assert Path(report['output_path']).suffix == suffix
        assert report['generated_levels'] == 0 and not report['reencoded']
        assert report['all_compressed_blocks_verified']
        assert report['source_output_pixel_regions_verified'] >= 24
        assert report['source_vendor'] == ['aperio','hamamatsu','philips'][row]
        assert report['icc_profile_copied'] == (row != 1)
        w.table.selectRow(row)
        w.show_selection()
        if row == 1:
            assert 'NDPI' in w.details.toPlainText()
            assert not report['all_output_tiles_verified']
    assert len(list(Path(folder).rglob('*.csv'))) == 1
    assert len({w.results[row]['directory'] for row in range(3)}) == 1
    print('Native batch verified:', [(r['report']['format'], r['report']['size_bytes'],
          r['report']['source_output_pixel_regions_verified']) for r in w.results.values()])
    w.clear()
assert [digest(path) for path in sources] == before
w.close()
print('Real SVS/NDPI/Philips GUI batch: native formats, ICC, all levels, common CSV, metadata and source SHA256 passed')
