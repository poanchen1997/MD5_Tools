@echo off
setlocal
:: Remember to adjust the path of Python 
set "PY=C:/Users/user/Downloads/Work/MD5_Tools/.venv/Scripts/python.exe"

REM 清快取
rmdir /s /q build dist 2>nul
del /q md5_folder_tool.spec 2>nul

REM 打包
"%PY%" -m PyInstaller --clean --noconfirm ^
  --name "MD5FolderTool" ^
  --onefile --windowed ^
  --icon "Assets\Instant Icon.ico" ^
  --add-data "Assets;Assets" ^
  md5_folder_tool.py

echo.
echo Done. Output: .\dist\MD5FolderTool.exe
pause
