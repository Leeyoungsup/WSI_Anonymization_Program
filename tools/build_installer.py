"""Build an offline per-user installer from a verified Windows release folder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def prepare_licenses(original, destination):
    """Preserve the vendor file; generate Unicode display copies and translation."""
    raw = original.read_bytes()
    # Translation is specific to this supplied SDK license, not future revisions.
    if hashlib.sha256(raw).hexdigest() != '5b9df9315e486600bcda51f6cd03bafc565113acba670a872cbbcfda8d61b862':
        raise ValueError('Philips EULA changed: review encoding and Korean translation before packaging')
    english = raw.decode('cp1252').replace('\r\r\n', '\n').replace('\r\n', '\n')
    korean = (ROOT/'docs/philips_eula_ko.txt').read_text(encoding='utf-8')
    bilingual = korean + '\n\n' + '=' * 64 + '\n영문 원문 / ORIGINAL ENGLISH AGREEMENT\n' + '=' * 64 + '\n\n' + english
    documents = {'PHILIPS_EULA_EN.txt': english, 'PHILIPS_EULA_KO.txt': korean,
                 'PHILIPS_EULA_KO_EN.txt': bilingual}
    for name, content in documents.items():
        if '\ufffd' in content:
            raise ValueError('Invalid Unicode replacement character in license: ' + name)
        (destination/name).write_text(content, encoding='utf-8-sig', newline='\r\n')
    return tuple(documents)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-dir', type=Path, default=ROOT/'release/WSI_Anonymization-1.10.2-Windows-x64-Research')
    parser.add_argument('--iscc', type=Path)
    args = parser.parse_args()
    release = args.release_dir.resolve()
    info = json.loads((release/'BUILD_INFO.json').read_text(encoding='utf-8'))
    if digest(release/'WSI_Anonymization.exe') != info['exe_sha256']:
        raise ValueError('Release EXE does not match BUILD_INFO.json')
    # Documentation may evolve independently; reject stale executable/bridge code.
    for name, expected in info['application_sources_sha256'].items():
        if Path(name).suffix == '.py' and not name.replace('\\','/').startswith('tools/build_'):
            if digest(ROOT/name) != expected:
                raise ValueError('Rebuild the application release after changing: '+name)
    for name, expected in info['philips_runtime']['files_sha256'].items():
        if digest(release/'philips'/name) != expected:
            raise ValueError('Philips runtime does not match manifest: '+name)
    guide=ROOT/'output/pdf/MeDIAuto_WSI_User_Guide_KO.pdf'
    if not guide.is_file():
        raise FileNotFoundError('Generate the PDF user guide before building the installer')
    candidates=[args.iscc] if args.iscc else [Path(os.environ.get('ISCC','ISCC.exe')),
        Path('C:/Program Files (x86)/Inno Setup 6/ISCC.exe'),Path('C:/Program Files/Inno Setup 6/ISCC.exe')]
    compiler=next((p for p in candidates if p.is_file()),None)
    if compiler is None:
        located=shutil.which('ISCC.exe')
        compiler=Path(located) if located else None
    if compiler is None:
        raise FileNotFoundError('Install Inno Setup 6 or pass --iscc')
    (ROOT/'build').mkdir(exist_ok=True)
    output=ROOT/'release'
    with tempfile.TemporaryDirectory(prefix='installer_payload_',dir=ROOT/'build') as temp:
        stage=Path(temp)
        shutil.copytree(release,stage,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copy2(guide,stage/guide.name)
        shutil.copy2(ROOT/'docs/installer_readme.txt',stage/'INSTALL_README.txt')
        license_names = prepare_licenses(stage/'philips/EULA.txt', stage)
        with Image.open(ROOT/'logo/icon.png') as icon:
            icon.save(stage/'setup.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(256,256)])
        with zipfile.ZipFile(stage/'source-build.zip','a',zipfile.ZIP_DEFLATED) as archive:
            for name in ('installer/WSI_Anonymization.iss','tools/build_installer.py','docs/installer_readme.txt','docs/philips_eula_ko.txt'):
                archive.write(ROOT/name,name)
        subprocess.run([str(compiler),'/Qp',f'/DPayloadDir={stage}',f'/DAppVersion={info["version"]}',
                        f'/DOutputPath={output}',str(ROOT/'installer/WSI_Anonymization.iss')],check=True)
        for name in license_names:
            shutil.copy2(stage/name,output/name)
    setup=output/f'MeDIAuto-WSI-{info["version"]}-Windows-x64-Setup.exe'
    checksum=digest(setup)
    setup.with_suffix('.exe.sha256').write_text(checksum+'  '+setup.name+'\n',encoding='ascii')
    # Installation instructions must be readable before running the installer.
    shutil.copy2(guide,output/guide.name)
    print(json.dumps({'installer':str(setup),'bytes':setup.stat().st_size,'sha256':checksum},indent=2))

if __name__=='__main__':
    main()
