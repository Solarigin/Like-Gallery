[Setup]
AppName=Social Image Archiver
AppVersion=0.1.0
DefaultDirName={pf64}\SIA
DefaultGroupName=SIA
UninstallDisplayIcon={app}\SIA.exe
OutputBaseFilename=SIA-Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\SIA.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Social Image Archiver"; Filename: "{app}\SIA.exe"
Name: "{commondesktop}\Social Image Archiver"; Filename: "{app}\SIA.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "其他任务"; Flags: unchecked
