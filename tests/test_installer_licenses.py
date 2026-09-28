"""Check Unicode display copies against untouched vendor license bytes."""
import hashlib
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from build_installer import prepare_licenses

original = ROOT/'build/philips_runtime/EULA.txt'
before = original.read_bytes()
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    names = prepare_licenses(original, folder)
    text = {}
    for name in names:
        data = (folder/name).read_bytes()
        assert data.startswith(b'\xef\xbb\xbf')
        text[name] = data.decode('utf-8-sig').replace('\r\n', '\n')
        assert '\ufffd' not in text[name]
    english = text['PHILIPS_EULA_EN.txt']
    expected = before.decode('cp1252').replace('\r\r\n', '\n').replace('\r\n', '\n')
    assert english == expected
    assert '“Agreement”' in english and '• You may terminate' in english
    assert '밃greement' not in english
    assert text['PHILIPS_EULA_KO_EN.txt'].endswith(english)
    assert text['PHILIPS_EULA_KO_EN.txt'].startswith(text['PHILIPS_EULA_KO.txt'])
    korean = text['PHILIPS_EULA_KO.txt']
    for section in ('General', 'What is the SDK?', 'Definitions', 'License grant',
                    'Ownership', 'No endorsement', 'License restrictions', 'Updates',
                    'Open Source Restrictions', 'Feedback', 'No Assignment',
                    'Term and Termination', 'Disclaimer', 'Indemnification',
                    'Limitation of Liability', 'Modification to terms', 'Miscellaneous'):
        assert '(' + section + ')' in korean, section
    changed = folder/'changed.txt'
    changed.write_bytes(before + b' changed')
    try:
        prepare_licenses(changed, folder)
    except ValueError:
        pass
    else:
        raise AssertionError('Stale translation accepted for a different license')
assert original.read_bytes() == before
print('License Unicode, complete sections, original preservation and changed-source rejection passed')
