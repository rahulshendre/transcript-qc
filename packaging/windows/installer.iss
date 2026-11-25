; Inno Setup script that turns the PyInstaller folder into one Transcript-QC-Setup.exe.
; build.ps1 runs it with the paths filled in:
;   iscc /DAppVersion=0.1.0 /DSourceDir=<dist\Transcript QC> /DOutputDir=<dist> installer.iss
; Installs for the current user only (no admin prompt), under %LOCALAPPDATA%\Programs,
; with a Start menu entry, an optional desktop shortcut and an uninstaller.

[Setup]
AppId={{AB16C9CE-D103-40F6-8270-FDC30AADC364}
AppName=Transcript QC
AppVersion={#AppVersion}
DefaultDirName={autopf}\Transcript QC
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Transcript-QC-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Transcript QC.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Transcript QC"; Filename: "{app}\Transcript QC.exe"
Name: "{autodesktop}\Transcript QC"; Filename: "{app}\Transcript QC.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Transcript QC.exe"; Description: "{cm:LaunchProgram,Transcript QC}"; Flags: nowait postinstall skipifsilent
