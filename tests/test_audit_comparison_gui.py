"""Synthetic-only GUI values must stay out of reports and CSV."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import numpy as np
import tifffile
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_app.gui import Window, STYLE, configure_qt, ROOT

configure_qt()
app = QApplication([])
for font in ("malgun.ttf", "malgunbd.ttf", "segoeui.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "inputs" / "example-slide.tiff"
    source.parent.mkdir()
    tifffile.imwrite(source, np.zeros((64, 128, 3), dtype=np.uint8), compression="jpeg", tile=(32, 32),
        photometric="rgb", metadata=None, description="DEMO_PATIENT_VALUE_123", software="DEMO_SCANNER_VALUE",
        datetime="2026:09:09 12:00:00")
    window = Window()
    window.show()
    window.add_paths([source])
    window.output.setText(str(root / "outputs"))
    window.include_filename.setChecked(False)
    window.copy_button.click()
    deadline = time.monotonic() + 60
    while window.process is not None:
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(.02)
    assert window.failed == 0, window.results
    result = window.results[0]
    original = window.audit_table.item(0, 1).data(Qt.UserRole)
    assert "DEMO_PATIENT_VALUE_123" in original
    assert "DEMO_PATIENT_VALUE_123" in window.audit_details.toPlainText()
    assert "DEMO_PATIENT_VALUE_123" not in json.dumps(result)
    assert "DEMO_SCANNER_VALUE" not in json.dumps(result)
    assert "DEMO_PATIENT_VALUE_123" not in Path(result["csv_path"]).read_text(encoding="utf-8-sig")
    assert b"DEMO_PATIENT_VALUE_123" not in Path(result["file"]).read_bytes()
    entries = result["report"]["anonymization_audit"]["entries"]
    assert entries[0]["before"] == "present" and entries[0]["after"] == "technical_metadata"
    assert window.side_tabs.currentIndex() == 2
    window.grab().save(str(ROOT / "artifacts" / "ui_before_after_demo.png"))
    window.clear()
    assert not window.source_display_values and window.audit_table.rowCount() == 0
    window.close()
print("Before/after table, GUI-only original values, CSV/TIFF exclusion and memory reset verified")
