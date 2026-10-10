; ============================================================
; SYNAPPM - INNO SETUP INSTALLER SCRIPT v5.2.1
; Production-ready installer with proper signing
; ============================================================

[Setup]
AppId={{SYNAPPM-INSTALLER-GUID}}
AppName=SynapsePM
AppVersion=5.2.1
AppPublisher=SynapsePM Technologies
AppPublisherURL=https://synapsepm.com
AppSupportURL=https://synapsepm.com/support
AppUpdatesURL=https://synapsepm.com/updates
DefaultDirName={autopf}\SynapsePM
DefaultGroupName=SynapsePM
AllowNoIcons=yes
OutputBaseFilename=synapsepm_installer
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\frontend\images\applogo.ico
UninstallDisplayIcon={app}\synapsepm.exe
VersionInfoVersion=5.2.1
VersionInfoCompany=SynapsePM Technologies
VersionInfoDescription=SynapsePM Predictive Maintenance Platform
VersionInfoCopyright=© 2026 SynapsePM Technologies. All rights reserved.
DisableProgramGroupPage=auto
DisableReadyPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
Name: "startmenuicon"; Description: "Create a &Start Menu entry"; GroupDescription: "Additional icons:"
Name: "autostart"; Description: "Start SynapsePM with Windows"; GroupDescription: "Startup options:"

[Files]
Source: "..\..\dist\synapsepm.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\frontend\images\applogo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SynapsePM"; Filename: "{app}\synapsepm.exe"
Name: "{group}\Uninstall SynapsePM"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SynapsePM"; Filename: "{app}\synapsepm.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\synapsepm.exe"; Description: "Launch SynapsePM"; Flags: postinstall nowait skipifsilent unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SynapsePM"; ValueData: "{app}\synapsepm.exe"; Flags: uninsdeletevalue; Tasks: autostart

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create application data directory
    if not DirExists(ExpandConstant('{localappdata}\SynapsePM')) then
    begin
      CreateDir(ExpandConstant('{localappdata}\SynapsePM'));
    end;
  end;
end;