"""Simple presets reach the real native worker; mixed inputs retain their formats."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile
import time
import numpy as np
import tifffile
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
with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as directory:
    root = Path(directory)
    source = root/'input'/'plain.tiff'
    source.parent.mkdir()
    tifffile.imwrite(source, np.full((128,128,3),120,dtype=np.uint8), tile=(128,128), compression='jpeg', photometric='ycbcr')
    w.add_paths([ROOT/'data/20260511_124345.i2syntax',source])
    assert w.storage_choice.currentData() == 'auto_original'
    assert not w.advanced_toggle.isChecked()
    assert not w.structure.isEnabled() and not w.preserve_mpp.isEnabled()
    w.storage_choice.setCurrentIndex(w.storage_choice.findData('auto_jpeg2000'))
    assert w.compression.currentData() == 'auto_jpeg2000' and w.structure.isEnabled()
    w.storage_choice.setCurrentIndex(w.storage_choice.findData('auto_original'))
    w.output.setText(str(root/'out'))
    w.include_filename.setChecked(False)
    w.start('copy')
    deadline = time.monotonic()+60
    while w.process is not None:
        app.processEvents()
        assert time.monotonic()<deadline
        time.sleep(.01)
    assert w.completed == 2 and w.failed == 0, w.results
    assert w.results[0]['report']['format'] == 'philips-isyntax'
    assert w.results[1]['report']['compression'] == 'jpeg-preserved'
    assert len(list((root/'out').rglob('*.isyntax'))) == 1
    assert len(list((root/'out').rglob('*.tiff'))) == 1
    w.table.selectRow(0)
    w.show_selection()
    assert 'iSyntax' in w.details.toPlainText()
w.close()
print('Simple GUI presets: Philips native + TIFF mixed export, geometry guards, status and results passed')
