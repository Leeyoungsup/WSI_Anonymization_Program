"""Three storage modes: availability and real native/preserved/lossless workers."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile
import time
import numpy as np
import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox
from wsi_app.gui import Window, configure_qt, ROOT, STYLE, storage_support
import wsi_app.gui as gui
if '--frozen' in sys.argv:
    gui.FROZEN = True
    gui.ROOT = ROOT/'dist'
    sys.executable = str(gui.ROOT/'WSI_Anonymization.exe')
configure_qt()
app = QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
app.setFont(QFont('Malgun Gothic', 10))
w = Window()
w.show()
def enabled():
    return [w.storage_choice.model().item(i).isEnabled() for i in range(3)]
def run():
    w.start('copy')
    deadline = time.monotonic() + 90
    while w.process is not None:
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(.01)
    assert w.completed == len(w.paths) and w.failed == 0, w.results
with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as directory:
    root = Path(directory)
    source = root/'input'/'plain.tiff'
    source.parent.mkdir()
    pixels = np.random.default_rng(71).integers(0, 256, (128,128,3), dtype=np.uint8)
    tifffile.imwrite(source, pixels, tile=(128,128), compression='jpeg', photometric='ycbcr')
    plain = source.with_name('uncompressed.tiff')
    tifffile.imwrite(plain, pixels, tile=(128,128), photometric='rgb')
    assert storage_support(plain)['preserve']
    for actual in list((ROOT/'data').glob('*.svs')) + list((ROOT/'data').glob('*.ndpi')):
        assert not storage_support(actual)['preserve'], actual.suffix
        assert not storage_support(actual)['native'], actual.suffix
    assert w.storage_choice.count() == 3
    w.add_paths([ROOT/'data/20260511_124345.i2syntax'])
    assert enabled() == [True, False, True]
    assert w.storage_choice.currentData() == 'native'
    assert not w.advanced_toggle.isChecked()
    assert not w.structure.isEnabled() and not w.preserve_mpp.isEnabled()
    dialogs = []
    def dismiss():
        box = app.activeModalWidget()
        assert isinstance(box, QMessageBox)
        dialogs.append(box.text())
        box.accept()
    QTimer.singleShot(30, dismiss)
    w.info_buttons['preset'].click()
    assert 'OpenSlide' in dialogs[-1] and 'Philips' in dialogs[-1]
    w.output.setText(str(root/'out'))
    w.include_filename.setChecked(False)
    run()
    assert w.results[0]['report']['format'] == 'philips-isyntax'
    w.add_paths([source])
    assert enabled() == [False, False, True]
    assert w.storage_choice.currentData() == 'jpeg2000'
    assert w.export_options()['compression'] == 'jpeg2000'
    w.storage_choice.setCurrentIndex(0)
    assert w.storage_choice.currentData() == 'jpeg2000'
    w.side_tabs.setCurrentIndex(0)
    app.processEvents()
    assert w.grab().save(str(ROOT/'artifacts/ui_storage_191_mixed.png'))
    w.storage_choice.showPopup()
    app.processEvents()
    assert w.storage_choice.view().grab().save(str(ROOT/'artifacts/ui_storage_191_choices.png'))
    w.storage_choice.hidePopup()
    w.clear()
    assert not w.copy_button.isEnabled()
    w.add_paths([source])
    assert enabled() == [False, True, True]
    w.storage_choice.setCurrentIndex(1)
    run()
    assert w.results[0]['report']['compression'] == 'jpeg-preserved'
    w.clear()
    w.add_paths([plain])
    assert enabled() == [False, False, True]
    run()
    assert w.results[0]['report']['compression'] == 'jpeg2000-lossless'
    np.testing.assert_array_equal(tifffile.imread(w.results[0]['file']), pixels)
    w.export_image.setChecked(False)
    assert not w.storage_choice.isEnabled() and w.copy_button.isEnabled()
    w.export_csv.setChecked(False)
    assert not w.copy_button.isEnabled()
w.close()
print('Three storage modes: availability, mixed batches, info, three real worker paths and pixel identity passed')
