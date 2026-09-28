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
        with Image.open(ROOT/'logo/icon.png') as icon:
            icon.save(stage/'setup.ico',format='ICO',sizes=[(16,16),(32,32),(48,48),(256,256)])
        with zipfile.ZipFile(stage/'source-build.zip','a',zipfile.ZIP_DEFLATED) as archive:
            for name in ('installer/WSI_Anonymization.iss','tools/build_installer.py','docs/installer_readme.txt'):
                archive.write(ROOT/name,name)
        subprocess.run([str(compiler),'/Qp',f'/DPayloadDir={stage}',f'/DAppVersion={info["version"]}',
                        f'/DOutputPath={output}',str(ROOT/'installer/WSI_Anonymization.iss')],check=True)
    setup=output/f'MeDIAuto-WSI-{info["version"]}-Windows-x64-Setup.exe'
    checksum=digest(setup)
    setup.with_suffix('.exe.sha256').write_text(checksum+'  '+setup.name+'\n',encoding='ascii')
    print(json.dumps({'installer':str(setup),'bytes':setup.stat().st_size,'sha256':checksum},indent=2))

if __name__=='__main__':
    main()
