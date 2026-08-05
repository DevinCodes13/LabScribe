; LabScribe Windows installer (Inno Setup).
;
; Compile with:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\labscribe.iss
; Output: installer\output\LabScribeSetup-<version>.exe
;
; Packages the existing PyInstaller one-folder build (dist\LabScribe\) into a
; normal Windows installer: Program Files install, Start Menu shortcut,
; optional Desktop shortcut, and a proper uninstaller. Deliberately does NOT
; touch %APPDATA%\LabScribe (settings, sessions, generated docs) on uninstall
; -- that's the user's data, not part of the app install.
;
; AppId is a fixed GUID (not regenerated per build) so a future version's
; installer recognizes this as an upgrade rather than a separate install.

#define MyAppName "LabScribe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "LabScribe"
#define MyAppExeName "LabScribe.exe"
#define MyAppURL "https://github.com/"

[Setup]
AppId={{127B1913-86B1-4E53-9804-864CCEE68E82}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
InfoBeforeFile=readme_before_install.txt
OutputDir=output
OutputBaseFilename=LabScribeSetup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; PyInstaller build is 64-bit (matches the 64-bit Python used to build it).
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Whole one-folder PyInstaller build: LabScribe.exe + its _internal runtime.
Source: "..\dist\LabScribe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Deliberately no [UninstallDelete] entries for %APPDATA%\LabScribe --
; settings, session history, and generated docs are the user's data and
; must survive an uninstall/reinstall or upgrade.
