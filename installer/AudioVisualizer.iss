#ifndef MyAppName
	#define MyAppName "Audio Visualizer"
#endif
#ifndef MyAppExeName
	#define MyAppExeName "AudioVisualizer.exe"
#endif
#ifndef MyAppVersion
	#define MyAppVersion "1.0.0"
#endif
#ifndef MyPublisher
	#define MyPublisher "Audio Visualizer"
#endif
#ifndef MyAppURL
	#define MyAppURL "https://example.com"
#endif

[Setup]
AppId={{6EC28E7F-0AF2-45EE-A6AB-D7904F374A4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\Audio Visualizer
DefaultGroupName=Audio Visualizer
OutputDir=..\dist
OutputBaseFilename=AudioVisualizer-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\assets\app_icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startup"; Description: "Start Audio Visualizer when I sign in"; GroupDescription: "Startup options:"; Flags: unchecked

[Files]
Source: "..\dist\AudioVisualizer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Audio Visualizer"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall Audio Visualizer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Audio Visualizer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Audio Visualizer"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AudioVisualizer"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: startup; Flags: uninsdeletevalue
