"""Rebuild a tissue-only iSyntax container; copy SDK compressed blocks verbatim."""
import os
import math
import hashlib
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
import pixelengine
import softwarerenderbackend
import softwarerendercontext
from sdk_slide import SDKSlide


HEADER_FIELDS = set("""DICOM_BITS_ALLOCATED DICOM_BITS_STORED DICOM_HIGH_BIT
DICOM_ICCPROFILE DICOM_LOSSY_IMAGE_COMPRESSION DICOM_LOSSY_IMAGE_COMPRESSION_METHOD
DICOM_LOSSY_IMAGE_COMPRESSION_RATIO DICOM_SAMPLES_PER_PIXEL DP_COLOR_MANAGEMENT
DP_WAVELET_DEADZONE DP_WAVELET_QUANTIZER DP_WAVELET_QUANTIZER_SETTINGS_PER_COLOR
DP_WAVELET_QUANTIZER_SETTINGS_PER_LEVEL PIM_DP_IMAGE_TYPE PIM_DP_SCANNED_IMAGES
PIM_DP_UFS_INTERFACE_VERSION UFS_IMAGE_BLOCK_COMPRESSION_METHOD UFS_IMAGE_BLOCK_COORDINATE
UFS_IMAGE_BLOCK_HEADERS UFS_IMAGE_BLOCK_HEADER_TEMPLATES UFS_IMAGE_BLOCK_HEADER_TEMPLATE_ID
UFS_IMAGE_CLUSTER_HEADER_TABLE UFS_IMAGE_CLUSTER_HEADER_TEMPLATES UFS_IMAGE_DIMENSIONS
UFS_IMAGE_DIMENSIONS_IN_BLOCK UFS_IMAGE_DIMENSIONS_IN_CLUSTER UFS_IMAGE_DIMENSIONS_OVER_BLOCK
UFS_IMAGE_DIMENSIONS_OVER_CLUSTER UFS_IMAGE_DIMENSION_DISCRETE_VALUES_STRING
UFS_IMAGE_DIMENSION_NAME UFS_IMAGE_DIMENSION_ORIGIN UFS_IMAGE_DIMENSION_RANGE
UFS_IMAGE_DIMENSION_RANGES UFS_IMAGE_DIMENSION_SCALE_FACTOR UFS_IMAGE_DIMENSION_TYPE
UFS_IMAGE_DIMENSION_UNIT UFS_IMAGE_GENERAL_HEADERS UFS_IMAGE_NUMBER_OF_BLOCKS
UFS_IMAGE_OPP_EXTREME_VERTEX UFS_IMAGE_OPP_EXTREME_VERTICES UFS_IMAGE_PIXEL_TRANSFORM_METHOD
UFS_IMAGE_VALID_DATA_ENVELOPES UFS_IMAGE_VALID_DATA_ENVELOPE_DIMENSIONS""".split())


def read_header(path):
    header = bytearray()
    with Path(path).open('rb') as stream:
        while len(header) < 32 * 1024**2:
            chunk = stream.read(65536)
            if not chunk:
                raise ValueError('Missing iSyntax header terminator')
            header.extend(chunk.split(b'\x04', 1)[0])
            if b'\x04' in chunk:
                break
        else:
            raise ValueError('iSyntax header exceeds validation limit')
    if b'<!DOCTYPE' in header or b'<!ENTITY' in header:
        raise ValueError('Unsupported XML declaration')
    return ET.fromstring(bytes(header))


def validate_header(path, icc, source_path):
    root = read_header(path)
    if {n.tag for n in root.iter()} - {'DataObject', 'Attribute', 'Array'}:
        raise ValueError('Unexpected iSyntax XML element')
    for node in root.iter('Attribute'):
        if node.get('Name') not in HEADER_FIELDS:
            raise ValueError('Unexpected iSyntax metadata field')
        if node.get('Name') == 'DICOM_ICCPROFILE':
            value = ''.join(node.itertext()).strip()
            if value != (icc or ''):
                raise ValueError('iSyntax ICC metadata mismatch')
    # Identical compressed bytes need identical wavelet quantization parameters.
    # Examine only the technical subtree; never log or return original XML values.
    def canonical(node):
        return (node.tag, node.get('Name'), (node.text or '').strip(),
                tuple(canonical(child) for child in node))
    def quantizers(tree):
        return [canonical(n) for n in tree.iter('Attribute')
                if n.get('Name') == 'DP_WAVELET_QUANTIZER_SETTINGS_PER_COLOR']
    if quantizers(root) != quantizers(read_header(source_path)):
        raise ValueError('Native wavelet quantization parameters changed')


def export_native(source, path, preserve_icc, workers, progress):
    """No source XML/text or associated images are copied. Source stays read-only."""
    path = Path(path).resolve()
    if not path.name.isascii():
        raise ValueError('Native export requires an ASCII temporary basename')
    src = source.image
    view = src.source_view
    ranges = view.dimension_ranges(0)
    if (view.dimension_names != ['x', 'y', 'component'] or
            any(r[0] != 0 or r[1] != 1 for r in ranges) or ranges[2][2] != 2 or
            src.compressor not in ('hulsken', 'hulsken2') or src.pixel_transform != 'legall53' or
            src.colorspace_transform != 'RGB2YCoCg' or src.quality_preset not in ('Q0', 'Q1', 'Q2') or
            view.bits_stored != 9 or src.block_size() != [128, 128, 1, 1, 3]):
        raise ValueError('Unsupported native Philips block layout')
    if any(not math.isfinite(v) for v in view.origin + view.scale) or any(v <= 0 for v in view.scale):
        raise ValueError('Invalid native geometry')
    pe = pixelengine.PixelEngine(softwarerenderbackend.SoftwareRenderBackend(),
                                softwarerendercontext.SoftwareRenderContext())
    output = pe['out']
    os.chdir(str(path.parent))
    opened = False
    try:
        output.open(path.name, 'ficom', 'w')
        opened = True
        parameters = (pe.WSICompressionParametersBuilder([r[2]+1 for r in ranges])
            .with_compressor(src.compressor).with_pixel_transform(src.pixel_transform)
            .with_colorspace_transform(src.colorspace_transform).with_quality_preset(src.quality_preset)
            .with_bit_depth(view.bits_stored).with_block_size('128x128')
            .with_num_derived_levels(view.num_derived_levels).with_scale(view.scale)
            .with_origin(view.origin).with_num_threads(workers).build())
        image = output.add_sub_image(parameters)
        icc = src.icc_profile if preserve_icc else ''
        if icc:
            image.icc_profile = icc
        rectangles = view.data_envelopes(0).as_rectangles()
        for x0,x1,y0,y1 in rectangles:
            image.include_input_region([x0,y0,0], [x1-x0+1,y1-y0+1,3], 0)
        for x0,x1,y0,y1 in rectangles:
            image.preallocate_pixels([x0,y0,0], [x1-x0+1,y1-y0+1,3], 0)
        output.finalize_geometry_and_properties()
        coordinates = image.ordered_block_coordinates()
        original = src.ordered_block_coordinates()
        if len(coordinates) != len(original) or set(map(tuple, coordinates)) != set(map(tuple, original)):
            raise ValueError('Native block geometry changed')
        buffer = np.empty(4 * 1024**2, dtype=np.uint8)
        total = len(coordinates)
        for i, coordinate in enumerate(coordinates):
            if i % 256 == 0:
                progress('write', i, total)
            size = src.read_block(buffer, coordinate)
            if not 0 < size <= buffer.size:
                raise ValueError('Invalid native block length')
            image.put_block(buffer[:size], size)
        output.close()
        opened = False
        progress('write', total, total)
        validate_header(path, icc, source.path)
        check = SDKSlide(path)
        try:
            if (check.associated_images or check.pe['in'].num_images != 1 or
                    check.dimensions != source.dimensions or check.level_dimensions != source.level_dimensions or
                    check.icc != (source.icc if preserve_icc else None)):
                raise ValueError('Native output geometry/ICC changed')
            cv = check.image.source_view
            for name in ('bits_stored', 'bits_allocated', 'pixel_representation', 'scale', 'origin'):
                if getattr(cv, name) != getattr(view, name):
                    raise ValueError('Native pixel representation changed')
            for name in ('compressor', 'quality_preset', 'pixel_transform', 'colorspace_transform',
                         'lossy_image_compression', 'lossy_image_compression_method',
                         'lossy_image_compression_ratio', 'color_linearity'):
                if getattr(check.image, name) != getattr(src, name):
                    raise ValueError('Native compression settings changed')
            other = np.empty_like(buffer)
            digest = hashlib.sha256()
            for i, coordinate in enumerate(coordinates):
                if i % 256 == 0:
                    progress('verify', i, total)
                a = src.read_block(buffer, coordinate)
                b = check.image.read_block(other, coordinate)
                if a != b or not np.array_equal(buffer[:a], other[:b]):
                    raise ValueError('Native compressed block changed')
                digest.update(struct.pack('<5qQ', *coordinate, a))
                digest.update(buffer[:a].tobytes())
            decoded = 0
            # Decode sampled regions of every level. Compressed blocks are ALL compared above.
            for level, (w,h) in enumerate(check.level_dimensions):
                size = (min(w,256), min(h,256))
                step = check.level_downsamples[level]
                for fx,fy in ((0,0),(.5,.5),(1,1)):
                    pos = (int((w-size[0])*fx)*step, int((h-size[1])*fy)*step)
                    with check.read_region(pos, level, size) as region:
                        region.load()
                        if preserve_icc:
                            with source.read_region(pos, level, size) as original_region:
                                if not np.array_equal(np.asarray(region), np.asarray(original_region)):
                                    raise ValueError('Native displayed pixels changed with retained ICC')
                    decoded += 1
            progress('verify', total, total)
            return {'verified_blocks': total, 'compressed_blocks_sha256': digest.hexdigest(),
                    'sampled_regions_decoded': decoded, 'display_pixels_compared': bool(preserve_icc),
                    'codec': src.compressor, 'quality_preset': src.quality_preset,
                    'header_whitelist_verified': True, 'level_dimensions': check.level_dimensions}
        finally:
            check.close()
    except BaseException:
        if opened:
            output.abort()
            output.close()
        raise
