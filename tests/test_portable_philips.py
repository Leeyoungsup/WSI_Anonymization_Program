"""Standalone SDK runtime test: no Conda/Python PATH, no existing user home."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import psutil

ROOT = Path(__file__).resolve().parents[1]
runtime = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "build/philips_runtime"
with tempfile.TemporaryDirectory(prefix="portable_sdk_test_") as directory:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CONDA", "PYTHON", "PHILIPS", "_PYI", "_MEI"))}
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    env["USERPROFILE"] = directory
    env["WSI_PHILIPS_SCRATCH"] = directory
    process = subprocess.Popen([str(runtime / "python.exe"), "-I", "-u", str(runtime / "bridge/export_server.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=env, cwd=directory, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        process.stdin.write(json.dumps({"command": "open", "path": str(ROOT / "data/20260511_124345.i2syntax")}) + "\n")
        process.stdin.flush()
        # communicate with close also places a finite timeout on the open/decode.
        # Inspect module provenance while the persistent reader is open.
        import threading, queue
        messages = queue.Queue()
        threading.Thread(target=lambda: messages.put(process.stdout.readline()), daemon=True).start()
        response = json.loads(messages.get(timeout=30))
        assert response["ok"], response
        assert response["data"]["dimensions"] == [51996, 22145]
        modules = [Path(m.path) for m in psutil.Process(process.pid).memory_maps() if m.path.lower().endswith((".dll", ".pyd"))]
        assert not any(".conda" in str(p).lower() or "anaconda" in str(p).lower() for p in modules)
        assert (runtime / "python37.dll") in modules
        assert (runtime / "lib/pixelengine/pixelengine.dll") in modules
        process.stdin.write('{"command":"close"}\n')
        process.stdin.flush()
        process.wait(timeout=10)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
print("Portable Philips: isolated Python, fake home, OS-only PATH and loaded DLL provenance passed")
