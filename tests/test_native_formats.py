"""Native SVS/NDPI: independent readback, PHI exclusion, failure atomicity, >4 GiB offsets."""
from pathlib import Path
import csv
import hashlib
import os
import struct
import sys
import tempfile
import numpy as np
import tifffile
import imagecodecs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi, _ndpi_directory, _openslide, ExportCancelled

ROOT = Path(__file__).resolve().parents[1]
openslide, dll = _openslide()
pixels = np.random.default_rng(67).integers(0, 256, (64, 64, 3), dtype=np.uint8)
encoded = imagecodecs.jpeg_encode(pixels, level=90, colorspace='RGB', outcolorspace='YCbCr', subsampling='444')
sentinel = b'PATIENT_NATIVE_SENTINEL_987'
comment = b'\xff\xfe' + struct.pack('>H', len(sentinel) + 2) + sentinel

def ndpi_fixture(path, *, high_offset=False, bad_scan=False, icc=False):
    jpeg = encoded[:2] + comment + encoded[2:]
    if bad_scan:
        jpeg = jpeg[:-2] + comment + jpeg[-2:]
    with path.open('w+b') as stream:
        stream.write(b'II\x2a\0' + b'\0' * 8)
        if high_offset:
            if os.name == 'nt':
                import ctypes
                import msvcrt
                returned = ctypes.c_ulong()
                assert ctypes.windll.kernel32.DeviceIoControl(
                    ctypes.c_void_p(msvcrt.get_osfhandle(stream.fileno())), 0x900C4,
                    None, 0, None, 0, ctypes.byref(returned), None)
            stream.seek(2**32 + 4096)
        offset = stream.tell()
        stream.write(jpeg)
        def tag(code, kind, fmt, *values):
            return code, kind, len(values), struct.pack('<' + fmt * len(values), *values)
        tags = [tag(256, 4, 'I', 64), tag(257, 4, 'I', 64), tag(258, 3, 'H', 8, 8, 8),
                tag(259, 3, 'H', 7), tag(262, 3, 'H', 6), (271, 2, 10, b'Hamamatsu\0'), (273, 4, 1, offset),
                tag(277, 3, 'H', 3), tag(278, 4, 'I', 64), (279, 4, 1, len(jpeg)),
                (282, 5, 1, struct.pack('<II', 20000, 1)),
                (283, 5, 1, struct.pack('<II', 20000, 1)), tag(296, 3, 'H', 3),
                tag(65420, 3, 'H', 1), tag(65421, 11, 'f', 20), tag(65424, 9, 'i', 0),
                (65427, 2, len(sentinel) + 1, sentinel + b'\0'),
                (65449, 2, len(sentinel) + 1, sentinel + b'\0')]
        if icc:
            tags.append((34675, 7, len(sentinel), sentinel))
        _ndpi_directory(stream, tags, 4)

def compare(source, result, vendor):
    with openslide.OpenSlide(str(source)) as a, openslide.OpenSlide(result['output_path']) as b:
        assert b.properties['openslide.vendor'] == vendor
        assert a.level_dimensions == b.level_dimensions
        assert not b.associated_images
        for key in ('openslide.mpp-x', 'openslide.mpp-y', 'openslide.objective-power'):
            assert a.properties.get(key) == b.properties.get(key)
        assert not any('PATIENT_NATIVE' in value for value in b.properties.values())
        for level in range(b.level_count):
            np.testing.assert_array_equal(np.asarray(a.read_region((0, 0), level, (32, 32))),
                                          np.asarray(b.read_region((0, 0), level, (32, 32))))
        b.get_thumbnail((128,128)).load()
    assert result['native_format_preserved'] and not result['reencoded']
    assert result['generated_levels'] == 0 and result['all_compressed_blocks_verified']

with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as folder:
    root = Path(folder)
    source = root/'synthetic.ndpi'
    ndpi_fixture(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    result = anonymize_wsi(source, root/'out', compression='native', rename_output=False, include_filename=False)
    compare(source, result, 'hamamatsu')
    assert sentinel not in Path(result['output_path']).read_bytes()
    assert hashlib.sha256(source.read_bytes()).digest() == before
    assert result['all_output_tiles_verified'] is False
    with Path(result['csv_path']).open(encoding='utf-8-sig', newline='') as f:
        row = next(csv.DictReader(f))
    assert row['original_filename'] == '' and row['output_filename'] == 'synthetic.ndpi'
    again = anonymize_wsi(source, root/'out', run_id=Path(result['directory']).name,
                         compression='native', rename_output=False, export_csv=False)
    assert Path(again['output_path']).name == 'synthetic_2.ndpi'
    for options in ({'pyramid': False}, {'preserve_mpp': False}, {'redactions': [(0,0,8,8)]}):
        try:
            anonymize_wsi(source, root/'bad-options', compression='native', **options)
            raise AssertionError('Incompatible native option accepted')
        except ValueError:
            pass
    high = root/'high.ndpi'
    ndpi_fixture(high, high_offset=True)
    assert high.stat().st_size > 2**32
    result = anonymize_wsi(high, root/'out', compression='native', export_csv=False)
    compare(high, result, 'hamamatsu')
    assert result['size_bytes'] < 10000
    broken = root/'broken.ndpi'
    ndpi_fixture(broken, bad_scan=True)
    try:
        anonymize_wsi(broken, root/'bad-scan', compression='native')
        raise AssertionError('Unexpected scan metadata was retained')
    except ValueError as error:
        assert 'marker inside NDPI JPEG scan' in str(error), str(error)
    assert not list((root/'bad-scan').rglob('*.ndpi'))
    with_icc = root/'icc.ndpi'
    ndpi_fixture(with_icc, icc=True)
    try:
        anonymize_wsi(with_icc, root/'bad-icc', compression='native', preserve_icc=True)
        raise AssertionError('Unsupported native NDPI ICC was silently dropped')
    except ValueError as error:
        assert 'ICC preservation' in str(error)
    ticks = [0]
    def cancel():
        ticks[0] += 1
        return ticks[0] > 2
    try:
        anonymize_wsi(source, root/'cancel', compression='native', cancelled=cancel)
        raise AssertionError('Cancellation ignored')
    except ExportCancelled:
        pass
    assert not list((root/'cancel').rglob('*.ndpi'))
    svs = root/'synthetic.svs'
    with tifffile.TiffWriter(svs, bigtiff=True) as writer:
        writer.write(pixels, tile=(32,32), compression='jpeg', photometric='ycbcr', metadata=None,
                     description='Aperio Image Library|AppMag=20|MPP=0.5|Patient=' + sentinel.decode())
        writer.write(pixels, compression='jpeg', photometric='ycbcr', metadata=None,
                     description='Aperio Image Library\nlabel', subfiletype=1)
    result = anonymize_wsi(svs, root/'out', compression='native', include_filename=False)
    compare(svs, result, 'aperio')
    assert Path(result['output_path']).suffix == '.svs'
    assert sentinel not in Path(result['output_path']).read_bytes()
    assert result['all_output_tiles_verified'] is True
    assert not list(root.rglob('*.partial.*'))
if dll:
    dll.close()
print('Native SVS/NDPI: reader identity, coding preservation, PHI removal, >4 GiB offsets, CSV/collisions/cancel/failure cleanup passed')
