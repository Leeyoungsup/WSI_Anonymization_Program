"""Integration check against local samples. Run from the project root."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "windows" if os.name == "nt" else "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from wsi_app.gui import Window, STYLE, ROOT, configure_qt


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def wait(app, window, timeout=180):
    until = time.monotonic() + timeout
    while window.process is not None:
        app.processEvents()
        if time.monotonic() > until:
            raise TimeoutError("GUI worker timed out")
        time.sleep(0.02)
    app.processEvents()


def main():
    configure_qt()
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    window.sample_button.click()
    assert len(window.paths) == 2, "Expected the two local samples"
    original = {p: digest(p) for p in window.paths}
    window.inspect_button.click()
    wait(app, window)
    assert window.failed == 0
    assert len(window.previews) == 2
    assert all(not x["errors"] for x in window.results.values())
    print("GUI inspection passed for both samples", flush=True)
    window.table.selectRow(0)
    app.processEvents()
    (ROOT / "artifacts").mkdir(exist_ok=True)
    assert window.grab().save(str(ROOT / "artifacts/gui_inspection.png"))
    with tempfile.TemporaryDirectory(prefix="gui_test_", dir=ROOT / "artifacts") as folder:
        window.output.setText(folder)
        window.copy_button.click()
        wait(app, window)
        assert window.failed == 0, window.results
        for item in window.results.values():
            assert Path(item["file"]).is_file()
            assert item["report"]["compressed_tissue_sha256_match"]
            assert item["report"]["status"] == "review_required"
        assert not list(Path(folder).glob(".pending_*"))
        print("GUI copies, compressed payload comparison and readback passed", flush=True)
        window.output.setText(str(ROOT / "data"))
        window.copy_button.click()
        wait(app, window)
        assert window.failed == 2, "Input folder output must be rejected"
        assert window.copy_button.isEnabled()
        print("Unsafe output path rejection and UI recovery passed", flush=True)
        window.inspect_button.click()
        window.cancel_button.click()
        wait(app, window)
        assert window.completed == 1
        assert window.inspect_button.isEnabled()
        print("Cancellation between files passed", flush=True)
        corrupt = Path(folder) / "corrupt.svs"
        corrupt.write_bytes(b"not a slide")
        window.clear_button.click()
        window.add_paths([corrupt])
        window.inspect_button.click()
        wait(app, window)
        assert window.failed == 1
        assert window.inspect_button.isEnabled()
        print("Corrupt input and UI recovery passed", flush=True)
    assert all(digest(p) == value for p, value in original.items())
    print("Full original-file SHA-256 unchanged for both samples", flush=True)
    window.close()


if __name__ == "__main__":
    main()
