$ErrorActionPreference = "Stop"

Write-Host "==> 清理输出"
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue

Write-Host "==> 使用 PyInstaller 打包"
pyinstaller --noconfirm --onefile --name SIA --add-data "gallery.html;." src\sia\app.py

Write-Host "==> 生成 Inno Setup 安装包"
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" scripts\installer.iss
