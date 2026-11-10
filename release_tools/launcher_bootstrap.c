/* Native Windows GUI entry for the portable Python application.
 * No shell, global Python, PATH lookup, installation, or elevation requested.
 */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>

static int exists(const wchar_t *file) {
    DWORD attr=GetFileAttributesW(file);
    return attr!=INVALID_FILE_ATTRIBUTES && !(attr&FILE_ATTRIBUTE_DIRECTORY);
}

int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,LPWSTR args,int show) {
    wchar_t root[32768],python[32768],script[32768],command[32768],entry[32768];
    DWORD count=GetModuleFileNameW(NULL,root,32768);
    (void)instance;(void)previous;(void)show;
    if(!count||count>=32768)return 2;
    wchar_t *slash=wcsrchr(root,L'\\');if(!slash)return 2;*slash=0;
    if(swprintf_s(python,32768,L"%s\\runtime\\pythonw.exe",root)<0 ||
       swprintf_s(script,32768,L"%s\\app.pyw",root)<0 ||
       swprintf_s(entry,32768,L"%s\\frontend\\dist\\index.html",root)<0)return 2;
    if(!exists(python)||!exists(script)||!exists(entry)) {
        if(wcscmp(args,L"--check")!=0)
            MessageBoxW(NULL,L"程序文件不完整。请将整个发布压缩包解压后运行，不要只复制 EXE。",L"启动失败",MB_OK|MB_ICONERROR);
        return 3;
    }
    if(wcscmp(args,L"--check")==0)return 0;
    if(swprintf_s(command,32768,L"\"%s\" -B \"%s\"",python,script)<0)return 2;
    STARTUPINFOW startup={0};PROCESS_INFORMATION process={0};startup.cb=sizeof(startup);
    if(!CreateProcessW(python,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,root,&startup,&process)) {
        MessageBoxW(NULL,L"无法启动内置运行环境，请确认文件已完整解压且目录可读取。",L"启动失败",MB_OK|MB_ICONERROR);
        return 4;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess,INFINITE);
    DWORD status=0;GetExitCodeProcess(process.hProcess,&status);CloseHandle(process.hProcess);
    return (int)status;
}
