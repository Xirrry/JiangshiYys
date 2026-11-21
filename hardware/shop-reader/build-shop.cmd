@echo off
call "D:\App\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 exit /b 1
cl /nologo /utf-8 /LD /O2 /MT shop_agent.c /Feshop_agent.dll /link /DYNAMICBASE /NXCOMPAT
exit /b %errorlevel%
