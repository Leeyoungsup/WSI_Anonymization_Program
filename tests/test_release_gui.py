"""Exercise GUI's frozen file channels against the real EXE, without desktop input."""
import csv
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import numpy as np
import tifffile
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
import wsi_app.gui as gui
ROOT = Path(__file__).resolve().parents[1]
exe = ROOT / "dist" / "WSI_Anonymization.exe"
gui.configure_qt()
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(gui.STYLE)
with tempfile.TemporaryDirectory(prefix="release_gui_") as directory:
    folder=Path(directory)
    source=folder / "input" / "sample.tiff"
    source.parent.mkdir()
    tifffile.imwrite(source,np.full((128,256,3),170,dtype=np.uint8),compression="jpeg",tile=(128,128),photometric="rgb")
    with patch.object(gui,"FROZEN",True), patch.object(gui,"ROOT",exe.parent), patch.object(gui,"STATE_ROOT",folder / "state"), patch.object(sys,"executable",str(exe)):
        window=gui.Window()
        window.add_paths([source])
        window.output.setText(str(folder / "output"))
        window.copy_button.click()
        deadline=time.monotonic()+60
        while window.process is not None:
            app.processEvents()
            assert time.monotonic()<deadline, window.status.text()
            time.sleep(0.02)
        assert window.failed==0, window.results
        result=window.results[0]
        assert result["report"]["compression"]=="jpeg-preserved"
        assert window.audit_table.rowCount() >= 10
        assert window.audit_table.horizontalHeaderItem(1).text() == "원본"
        assert "익명화 결과" in window.audit_details.toPlainText()
        assert all(label in window.details.toPlainText() for label in ("Magnification:", "Pixel Size:", "MPP:", "Physical Size:"))
        assert Path(result["file"]).is_file()
        with Path(result["csv_path"]).open(encoding="utf-8-sig",newline="") as stream:
            assert next(csv.DictReader(stream))["output_filename"]==Path(result["file"]).name
        assert not list((folder / "state").rglob("*.json*"))
        window.close()
print("GUI frozen mode + packaged EXE: file channels, progress, TIFF/CSV results and job cleanup passed")
