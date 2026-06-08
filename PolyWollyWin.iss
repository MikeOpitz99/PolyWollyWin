#define MyAppName "PolyWollyWin"
#define MyAppVersion "2.6.5"
#define MyAppPublisher "Mike Opitz"
#define MyAppURL "https://github.com/MikeOpitz99/PolyWollyWin"
#define MyAppExeName "PolyWollyWin.exe"
#define SourceRoot "D:\programming\PolyWollyWin"
#define DistDir "D:\programming\PolyWollyWin\dist"
#define ReleaseDir "D:\programming\PolyWollyWin\releases"

[Setup]
AppId={{B9F2A3C1-4D7E-4F8A-9B2C-1E3D5F7A9B0C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright=Copyright (C) 2024 Mike Opitz
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
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
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
PrivilegesRequired=lowest



[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Run {#MyAppName} when Windows starts"; GroupDescription: "Windows Startup:"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#DistDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "{#SourceRoot}\CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

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
Type: files; Name: "{app}\PolyWollyWin.exe"
Type: files; Name: "{app}\README.md"
Type: files; Name: "{app}\CHANGELOG.md"
Type: files; Name: "{app}\LICENSE"
Type: dirifempty; Name: "{app}"
