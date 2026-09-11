"""Real native blocks, geometry/ICC, cancellation, collision and safe publication."""
import csv
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wsi_anonymizer import anonymize_wsi, ExportCancelled, PhilipsSlide

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(dir=ROOT / 'artifacts') as directory:
    root = Path(directory)
    samples = sorted((ROOT / 'data').glob('*.i2syntax'))
    for index, source in enumerate(samples):
        stat = source.stat()
        report = anonymize_wsi(source, root, compression='philips', include_filename=False,
                               preserve_icc=bool(index), rename_output=False)
        assert report['format'] == 'philips-isyntax'
        assert report['source_compressed_payload_copied'] and not report['reencoded']
        assert not report['additional_lossy_compression']
        assert report['all_compressed_blocks_verified'] and not report['all_output_tiles_verified']
        assert abs(report['size_bytes']-stat.st_size) < 100000
        assert report['native_validation']['header_whitelist_verified']
        assert report['native_validation']['sampled_regions_decoded'] >= 24
        assert report['metadata_clean'] == (not bool(index))
        assert Path(report['output_path']).name == source.stem+'.isyntax'
        with PhilipsSlide(report['output_path']) as slide:
            assert not slide.associated_images
            assert (slide.icc is not None) == bool(index)
            with slide.get_thumbnail((256,256)) as image:
                image.load()
        with Path(report['csv_path']).open(encoding='utf-8-sig', newline='') as stream:
            row = next(csv.DictReader(stream))
            assert row['original_filename'] == ''
            assert row['compression'] == 'philips-native-preserved'
        assert source.stat().st_mtime_ns == stat.st_mtime_ns
    # Never overwrite a prior result, including retained original names.
    run_id = '20260911_120000_000001'
    a = anonymize_wsi(samples[0], root, compression='philips', run_id=run_id, rename_output=False)
    b = anonymize_wsi(samples[0], root, compression='philips', run_id=run_id, rename_output=False)
    assert Path(a['output_path']).exists() and Path(b['output_path']).stem.endswith('_2')
    stopped = [False]
    def progress(event):
        if event['completed'] > 0:
            stopped[0] = True
    try:
        anonymize_wsi(samples[0], root / 'cancel', compression='philips', progress=progress,
                      cancelled=lambda: stopped[0])
        raise AssertionError('Cancellation ignored')
    except ExportCancelled:
        pass
    assert not list((root / 'cancel').rglob('*.isyntax'))
    for options in ({'preserve_mpp': False}, {'pyramid': False}, {'redactions': [(0,0,1,1)]}):
        try:
            anonymize_wsi(samples[0], root / 'reject', compression='philips', **options)
            raise AssertionError('Incompatible geometry accepted')
        except ValueError:
            pass
    assert not (root / 'reject').exists()
    assert not list(root.rglob('*.partial.isyntax'))
print('Native Philips: both full samples, blocks/ICC/geometry, CSV, collisions, cancellation and source integrity passed')
