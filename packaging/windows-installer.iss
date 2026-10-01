; Compile only the audited PyInstaller directory, never the project checkout.
#if VER != EncodeVer(6, 7, 3)
  #error Use the pinned Inno Setup 6.7.3 compiler
#endif
#ifndef AppVersion
  #error AppVersion must be supplied by scripts/build-windows.ps1
#endif
#ifndef BundleDir
  #error BundleDir must be supplied by scripts/build-windows.ps1
#endif
#ifndef ReleaseDir
  #error ReleaseDir must be supplied by scripts/build-windows.ps1
#endif
#ifndef IconFile
  #error IconFile must be supplied by scripts/build-windows.ps1
#endif
#define AppName "拾知学习空间"
#define AppExe "ShizhiStudyAssistant.exe"

[Setup]
AppId={{4DCF0D6A-05E9-4E1B-AC83-F2761A141DDD}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Shizhi Study Assistant
DefaultDirName={localappdata}\Programs\ShizhiStudyAssistant
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=shizhi-study-assistant-{#AppVersion}-windows-x64-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
DisableWelcomePage=no
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no
Uninstallable=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} 安装程序

[Languages]
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{group}\卸载{#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "启动{#AppName}"; Flags: nowait postinstall skipifsilent

; No user data is installed or deleted. The application stores it separately in
; %LOCALAPPDATA%\ShizhiStudyAssistant\data and \vault, including after uninstall.
