#define MyAppName "PIng"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PIng"
#define MyAppExeName "PIng.exe"

[Setup]
AppId={{7E698836-195A-46F3-84BB-5A5D34E38EA8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PIng
DefaultGroupName=PIng
DisableProgramGroupPage=yes
OutputDir=installer-output
OutputBaseFilename=PIng-Setup-{#MyAppVersion}
SetupIconFile=assets\ping.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Files]
Source: "dist\PIng\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PIng"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\PIng"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir PIng"; Flags: nowait postinstall skipifsilent
