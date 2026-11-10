@echo off
chcp 65001 >nul
call "D:\App\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0native-source"
rc /nologo /fo"%~dp0native-build\app.res" app.rc
if errorlevel 1 exit /b 1
cl /nologo /utf-8 /O2 /W4 /MT /guard:cf launcher_bootstrap.c "%~dp0native-build\app.res" /Fo"%~dp0native-build\entry.obj" /Fe"%~dp0native-build\僵尸痒痒鼠.exe" /link user32.lib /SUBSYSTEM:WINDOWS /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /MANIFEST:EMBED /MANIFESTUAC:"level='asInvoker' uiAccess='false'"
exit /b %errorlevel%
