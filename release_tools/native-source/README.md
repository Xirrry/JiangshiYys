原生 EXE 入口源码。打开 Visual Studio x64 开发者命令提示符，进入本目录，执行：

rc /fo app.res app.rc

cl /utf-8 /O2 /MT launcher_bootstrap.c app.res /link user32.lib /SUBSYSTEM:WINDOWS /DYNAMICBASE /NXCOMPAT /OUT:Launcher.exe

EXE 通过自身所在目录定位 runtime/pythonw.exe 和 app.pyw，不调用系统 Python、不依赖 PATH。完整目录需一起分发。
