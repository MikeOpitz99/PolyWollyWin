#define MyAppName "PolyWollyWin"
#define MyAppVersion "3.0.3"
#define MyAppPublisher "Mike Opitz"
#define MyAppURL "https://github.com/MikeOpitz99/PolyWollyWin"
#define MyAppExeName "PolyWollyWin.exe"

; SourcePath is the directory containing this .iss file.
#define SourceRoot SourcePath
#define DistDir AddBackslash(SourcePath) + "dist\PolyWollyWin"
#define ReleaseDir AddBackslash(SourcePath) + "releases"

[Setup]
AppId={{B9F2A3C1-4D7E-4F8A-9B2C-1E3D5F7A9B0C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright (C) 2026 Mike Opitz
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
MinVersion=10.0.17763
CloseApplications=yes
CloseApplicationsFilter=PolyWollyWin.exe
RestartApplications=no
OutputDir={#ReleaseDir}
OutputBaseFilename=PolyWollyWin-v{#MyAppVersion}-Setup
SetupIconFile={#SourceRoot}\assets\pww.ico

Compression=lzma2/ultra64
SolidCompression=yes

WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
PrivilegesRequired=lowest

VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Direct AniMe Matrix controller for the ROG Strix Flare II Animate
VersionInfoCopyright=Copyright (C) 2026 Mike Opitz
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Run {#MyAppName} when Windows starts"; GroupDescription: "Windows Startup:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "{#SourceRoot}\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\ACKNOWLEDGEMENTS.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#MyAppName}"; \
    ValueData: """{app}\{#MyAppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; \
    Parameters: "/f /im {#MyAppExeName}"; \
    Flags: runhidden; RunOnceId: "KillPolyWollyWin"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\README.md"
Type: files; Name: "{app}\CHANGELOG.md"
Type: files; Name: "{app}\LICENSE"
Type: files; Name: "{app}\ACKNOWLEDGEMENTS.md"
Type: dirifempty; Name: "{app}"
