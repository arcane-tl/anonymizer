; Inno Setup 6 script — Anonymizer for Windows
; Built by packaging/windows/build-release.ps1
;
; Defines (passed by ISCC or defaults):
;   MyAppVersion  e.g. 1.2.0
;   MyStageDir    absolute path to dist\windows-stage

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef MyStageDir
  #define MyStageDir "..\..\..\dist\windows-stage"
#endif

#define MyAppName "Anonymizer"
#define MyAppPublisher "anonymizer contributors"
#define MyAppURL "https://github.com/arcane-tl/anonymizer"
#define MyAppExeName "Anonymizer.exe"
; Logo for Setup wizard (path relative to this .iss file)
#define MySetupIcon "..\icons\Anonymizer.ico"

[Setup]
AppId={{A7B3C1D2-E4F5-6789-ABCD-EF0123456789}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Anonymizer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; Per-user install — no admin required
OutputDir=..\..\..\dist
OutputBaseFilename=Anonymizer-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#MySetupIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "addpath"; Description: "Add &CLI (anonymize) to your user PATH"; GroupDescription: "Command line:"; Flags: checkedonce

[Files]
; Full stage: GUI, runtime venv, bin launchers, VERSION
Source: "{#MyStageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Registry]
; PATH addition for bin\ (user environment)
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}\bin"; Tasks: addpath; \
  Check: NeedsAddPath(ExpandConstant('{app}\bin'))

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  { look for exact segment }
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Path, AppBin, NewPath: string;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  AppBin := ExpandConstant('{app}\bin');
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path) then
    exit;
  { remove ;app\bin or app\bin; or standalone }
  NewPath := Path;
  StringChangeEx(NewPath, ';' + AppBin, '', True);
  StringChangeEx(NewPath, AppBin + ';', '', True);
  if NewPath = AppBin then
    NewPath := '';
  if NewPath <> Path then
    RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', NewPath);
end;
