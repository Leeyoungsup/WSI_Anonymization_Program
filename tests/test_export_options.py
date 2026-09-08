"""Native GUI export choices, worker wiring and explanatory dialogs."""
import csv
from pathlib import Path
import sys
import tempfile
import time
import numpy as np
import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from wsi_app.gui import Window, STYLE, configure_qt, ROOT
from wsi_anonymizer import anonymize_wsi

def wait(app, window):
    deadline = time.monotonic() + 60
    while window.process is not None:
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(0.01)
    app.processEvents()
    assert window.failed == 0, window.results

configure_qt()
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
w = Window()
w.show()
with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as folder:
    root = Path(folder)
    inputs = root / "input"
    inputs.mkdir()
    for name in ("patient_a.tif", "patient_b.tif"):
        tifffile.imwrite(inputs / name, np.full((64, 80, 3), 123, dtype=np.uint8),
                         tile=(32, 32), photometric="rgb", compression="jpeg",
                         resolution=(40000,40000), resolutionunit="CENTIMETER")
    w.add_folder(inputs)
    w.output.setText(str(root / "out"))
    w.export_image.setChecked(False)
    w.export_csv.setChecked(False)
    assert not w.copy_button.isEnabled()
    w.start("copy")
    assert w.process is None
    w.export_csv.setChecked(True)
    w.include_filename.setChecked(False)
    assert not w.compression.isEnabled()
    w.copy_button.click()
    wait(app,w)
    result = w.results[1]
    assert result["file"] is None
    assert not list(Path(result["directory"]).glob("*.tiff"))
    with Path(result["csv_path"]).open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==2 and all(r["original_filename"]=="" for r in rows)
    assert all(r["mpp_x_um"]=="0.25" for r in rows)
    assert "CSV" in w.details.toPlainText()
    w.export_image.setChecked(True)
    w.export_csv.setChecked(False)
    w.preserve_mpp.setChecked(False)
    w.compression.setCurrentIndex(1)
    w.copy_button.click()
    wait(app,w)
    for result in w.results.values():
        assert result["csv_path"] is None
        assert result["report"]["compression"]=="deflate-lossless"
        assert result["report"]["mpp"] is None
        assert not list(Path(result["directory"]).glob("*.csv"))
    w.export_csv.setChecked(True)
    w.compression.setCurrentIndex(0)
    w.copy_button.click()
    wait(app,w)
    with Path(w.results[1]["csv_path"]).open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==2 and all(r["original_filename"]=="" for r in rows)
    assert all(r["compression"]=="jpeg-preserved" for r in rows)
    texts=[]
    def dismiss():
        box=app.activeModalWidget()
        assert isinstance(box,QMessageBox)
        texts.append(box.text())
        box.accept()
    for button in w.info_buttons.values():
        QTimer.singleShot(30,dismiss)
        button.click()
    assert len(texts)==len(w.info_buttons) and all(len(t)>30 for t in texts)
    w.clear()
    w.sample_button.click()
    w.output.setText(str(ROOT / "output"))
    w.include_filename.setChecked(True)
    w.preserve_mpp.setChecked(True)
    app.processEvents()
    assert w.grab().save(str(ROOT / "artifacts/gui_export_options.png"))
    for size in [(1050,850),(1240,980)]:
        w.resize(*size)
        app.processEvents()
        assert w.copy_button.isVisible() and w.options_box.height()>100
w.close()
print("Export combinations, CSV-only batch rows, filename exclusion, compression/MPP options, dialogs and GUI passed")
