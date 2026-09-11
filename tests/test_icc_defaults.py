"""Default ICC preservation across API, adapter and CLI; explicit opt-out remains."""
from pathlib import Path
import sys
import subprocess
import tempfile
import numpy as np
from PIL import ImageCms
import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi, _openslide
from wsi_app.engine import create_anonymized_tiff

ROOT = Path(__file__).resolve().parents[1]
openslide, dll = _openslide()
icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as folder:
    root = Path(folder)
    source = root/'input'/'sample.tiff'
    source.parent.mkdir()
    tifffile.imwrite(source, np.full((64,64,3), 120, dtype=np.uint8),
                     tile=(32,32), compression='jpeg', photometric='ycbcr', iccprofile=icc)
    report = anonymize_wsi(source, root/'api')
    assert report['icc_profile_copied'] and report['icc_review_required']
    assert not report['metadata_clean']
    with openslide.OpenSlide(report['output_path']) as slide:
        assert slide.read_region((0,0),0,(1,1)).info['icc_profile'] == icc
    for flag, name in (([], 'default'), (['--no-preserve-icc'], 'excluded')):
        result = subprocess.run([sys.executable, str(ROOT/'wsi_anonymizer.py'), str(source),
                                 str(root/name), *flag], capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        output = next((root/name).rglob('*.tiff'))
        with openslide.OpenSlide(str(output)) as slide:
            assert slide.read_region((0,0),0,(1,1)).info.get('icc_profile') == (None if flag else icc)
    # Adapter/worker defaults are checked via the real EXE in test_release.py.
    import inspect
    assert inspect.signature(create_anonymized_tiff).parameters['preserve_icc'].default is True
if dll:
    dll.close()
print('ICC defaults: API byte identity/report, CLI retain/opt-out and adapter default passed')
