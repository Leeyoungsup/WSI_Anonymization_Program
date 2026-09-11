"""The native metadata gate refuses patient fields and altered quantization."""
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT/'build/philips_runtime/python.exe'
script = r'''
from sdk_bootstrap import prime_sdk_dll_paths
prime_sdk_dll_paths()
from native_export import validate_header
from pathlib import Path
import tempfile,sys
source = Path(sys.argv[1])
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)/'bad.isyntax'
    for xml, error in (
        (b'<DataObject><Attribute Name="DICOM_PATIENT_NAME">PATIENT_SENTINEL</Attribute></DataObject>', 'Unexpected iSyntax metadata field'),
        (b'<DataObject><Attribute Name="DICOM_ICCPROFILE">unexpected</Attribute></DataObject>', 'iSyntax ICC metadata mismatch'),
        (b'<DataObject><Attribute Name="PIM_DP_IMAGE_TYPE">WSI</Attribute></DataObject>', 'Native wavelet quantization parameters changed'),
        (b'<!DOCTYPE a [<!ENTITY x "test">]><DataObject/>', 'Unsupported XML declaration'),
    ):
        path.write_bytes(xml+bytes([4]))
        try:
            validate_header(path, '', source)
            raise AssertionError('Unsafe or inconsistent header accepted')
        except ValueError as exc:
            assert str(exc) == error, str(exc)
print('Native header rejection: patient field, unexpected ICC, quantizer mismatch and entity declaration passed')
'''
subprocess.run([str(runtime), '-I', '-c', script, str(ROOT/'data/20260511_124345.i2syntax')], check=True)
