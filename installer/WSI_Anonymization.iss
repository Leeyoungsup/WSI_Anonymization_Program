; Compile through tools/build_installer.py. Payload is validated before compilation.
#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef OutputPath
  #error OutputPath is required
#endif

[Setup]
AppId={{A7513077-9C28-476B-9136-B2BBA0B72021}
AppName=MeDIAuto WSI Anonymization
AppVersion={#AppVersion}
AppPublisher=MeDIAuto
DefaultDirName={localappdata}\Programs\MeDIAuto WSI
DefaultGroupName=MeDIAuto WSI
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=MeDIAuto-WSI-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\WSI_Anonymization.exe
SetupIconFile={#PayloadDir}\setup.ico
InfoBeforeFile={#PayloadDir}\INSTALL_README.txt
LicenseFile={#PayloadDir}\philips\EULA.txt
CloseApplications=no
RestartApplications=no
DisableProgramGroupPage=yes
AllowNoIcons=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MeDIAuto WSI"; Filename: "{app}\WSI_Anonymization.exe"; WorkingDir: "{app}"
Name: "{group}\사용자 가이드"; Filename: "{app}\MeDIAuto_WSI_User_Guide_KO.pdf"
Name: "{group}\제거"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MeDIAuto WSI"; Filename: "{app}\WSI_Anonymization.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\WSI_Anonymization.exe"; Description: "{cm:LaunchProgram,MeDIAuto WSI}"; Flags: nowait postinstall skipifsilent
