"""Integration check against local samples. Run from the project root."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import numpy as np
import tifffile

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
        source_folder = Path(folder) / "input"
        source_folder.mkdir()
        sample = source_folder / "synthetic.tif"
        tifffile.imwrite(sample, np.full((320, 530, 3), 160, dtype=np.uint8),
                         tile=(128, 128), photometric="rgb", description="PRIVATE_SENTINEL")
        window.clear_button.click()
        window.add_paths([sample])
        window.output.setText(str(Path(folder) / "output"))
        window.copy_button.click()
        wait(app, window)
        assert window.failed == 0, window.results
        for item in window.results.values():
            assert Path(item["file"]).is_file()
            assert item["report"]["all_output_tiles_verified"]
            assert item["report"]["status"] == "metadata_clean_pixel_review_required"
            assert Path(item["file"]).suffix == ".tiff"
            assert b"PRIVATE_SENTINEL" not in Path(item["file"]).read_bytes()
        assert not list(Path(folder).glob(".pending_*"))
        print("GUI TIFF export, metadata removal and pixel verification passed", flush=True)
        window.reviewed.setChecked(True)
        window.copy_button.click()
        wait(app, window)
        assert window.results[0]["report"]["status"] == "metadata_clean_pixels_reviewed"
        print("Caller pixel-review assertion propagation passed", flush=True)
        window.output.setText(str(source_folder))
        window.copy_button.click()
        wait(app, window)
        assert window.failed == 1, "Input folder output must be rejected"
        assert window.copy_button.isEnabled()
        print("Unsafe output path rejection and UI recovery passed", flush=True)
        window.output.setText(str(Path(folder) / "output"))
        window.copy_button.click()
        window.cancel_button.click()
        wait(app, window)
        assert window.table.item(0, 3).text() == "중지됨"
        assert not list((Path(folder) / "output").glob(".pending_*"))
        print("TIFF cancellation and temporary-output cleanup passed", flush=True)
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
