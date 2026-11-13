@echo off
call "D:\App\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
cd /d "%~dp0"
cl /nologo /O2 /MT /LD mail_agent.c /link /OUT:mail_agent.dll
