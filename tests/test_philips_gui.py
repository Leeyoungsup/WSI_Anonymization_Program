"""Offscreen GUI: Philips selection, auto mode and mixed success/failure CSV batch."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from wsi_app.gui import Window, configure_qt, ROOT

configure_qt()
app = QApplication([])
window = Window()
with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as directory:
    window.add_paths(sorted((ROOT / "data").glob("*.i2syntax")))
    assert len(window.paths) == 2
    assert window.compression.currentData() == "native"
    assert window.storage_choice.currentData() == "native"
    assert not window.advanced_toggle.isChecked()
    window.output.setText(directory)
    window.export_image.setChecked(False)
    window.include_filename.setChecked(False)
    window.start("copy")
    deadline = time.monotonic() + 45
    while window.process is not None:
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert window.completed == 2 and window.failed == 0
    assert len(list(Path(directory).rglob("*.csv"))) == 1
    assert not list(Path(directory).rglob("*.tiff"))
    window.clear()
window.close()
print("Philips GUI: extensions, visible auto compression, success/failure batch and CSV-only passed")
