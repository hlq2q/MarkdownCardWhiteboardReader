; ============================================================================
;  Inno Setup 6 script for MarkdownCardWhiteboardReader (mcwr).
;
;  Compile through Packaging.bat (recommended) so that the version is stamped from the
;  project instead of being typed here:
;      Packaging.bat                       -> ISCC /DAppVersion=<mcwr.__version__> ...
;      ISCC.exe packaging\mcwr-installer.iss   (fallback: AppVersion stays 0.0.0)
;
;  Paths are relative to THIS file, so the script compiles from any working directory.
;  Languages: English only - Inno Setup does not ship a Simplified Chinese translation
;  (drop ChineseSimplified.isl next to the script and add it to [Languages] if wanted).
; ============================================================================

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppVersionQuad
  #define AppVersionQuad "0.0.0.0"
#endif
#ifndef AppName
  #define AppName "MarkdownCardWhiteboardReader"
#endif
#ifndef AppExeName
  #define AppExeName "mcwr.exe"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\mcwr"
#endif
#ifndef OutputDirName
  #define OutputDirName "Output"
#endif

; Fail at compile time instead of producing an installer with no program in it.
#if !FileExists(AddBackslash(SourcePath) + SourceDir + "\" + AppExeName)
  #error The bundle is missing: compile the project first, e.g. "Packaging.bat" (PyInstaller onedir puts it in dist\mcwr).
#endif

[Setup]
; ---------------------------------------------------------------------------
; AppId is the identity of this application. NEVER change it: a new setup.exe
; with the same AppId upgrades the previous installation in place, while a
; changed one would sit next to it in "Apps & features" forever.
; ---------------------------------------------------------------------------
AppId={{39396861-71C9-45A7-802A-7D6C0B97FCBC}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=hlq2q
VersionInfoVersion={#AppVersionQuad}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersionQuad}
DefaultDirName={autopf}\{#AppName}
DisableDirPage=auto
DisableProgramGroupPage=yes
DefaultGroupName={#AppName}
; Per-user installation by default (no UAC prompt). Run setup.exe /ALLUSERS from an elevated
; shell to install machine-wide instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDirName}
; The icon comes from the repository assets (relative to THIS script, like SourceDir above):
; the frozen exe embeds the same file, so the shortcut and the setup both show it.
SetupIconFile=..\src\mcwr\assets\mcwr.ico
OutputBaseFilename=mcwr-setup-{#AppVersion}
; The bundle is ~580 MB of Qt/WebEngine binaries; a versioned output name keeps every build.
#ifdef FAST
Compression=lzma2/fast
#else
Compression=lzma2/max
#endif
; Solid compression over ~580 MB inside a 32-bit compiler: let LZMA run in its own process
; (Inno Setup's documented advice for large installs; avoids out-of-memory compile failures).
SolidCompression=yes
LZMAUseSeparateProcess=yes
CompressionThreads=auto
WizardStyle=modern
SetupLogging=yes
UninstallDisplayIcon={app}\{#AppExeName}
; Close a running instance before replacing files, but do not restart it behind the user's back.
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no
AllowNoIcons=yes
; Data (\APPDATA\MarkdownCardWhiteboardReader) is user data, not part of the application:
; the uninstaller leaves it alone on purpose.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Read-only Markdown card whiteboard"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
