#define AppVersion "3.6.0"
[Setup]
AppId=AURA-IA-Nativa
AppName=AURA Inteligencia Artificial
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\AURA
DefaultGroupName=AURA
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=entrega
OutputBaseFilename=AURA-{#AppVersion}-Nativa-Instalador-Windows-x64
SetupIconFile=agente_ia\static\assets\aura.ico
UninstallDisplayIcon={app}\AURA-Nativa.exe
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
LicenseFile=LEEME-NATIVA.txt

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "dist\AURA-Nativa\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "modelos\*,voz\*,frameworks\npm-cache.zip"
Source: "runtime\modelos\*"; DestDir: "{app}\modelos"; Flags: ignoreversion recursesubdirs createallsubdirs nocompression
Source: "runtime\voz\*"; DestDir: "{app}\voz"; Flags: ignoreversion recursesubdirs createallsubdirs nocompression

Source: "runtime\frameworks\npm-cache.zip"; DestDir: "{app}\frameworks"; Flags: ignoreversion nocompression

[Icons]
Name: "{group}\AURA"; Filename: "{app}\AURA-Nativa.exe"
Name: "{autodesktop}\AURA"; Filename: "{app}\AURA-Nativa.exe"
Name: "{group}\Desinstalar AURA"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\AURA-Nativa.exe"; Description: "Abrir AURA"; Flags: nowait postinstall skipifsilent
