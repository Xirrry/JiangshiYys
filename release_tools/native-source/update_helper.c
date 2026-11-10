#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static wchar_t root[32768],job[32768],fresh[32768],backup[32768],failed[32768];
static int plain(const wchar_t *p){DWORD a=GetFileAttributesW(p);return a!=INVALID_FILE_ATTRIBUTES&&(a&FILE_ATTRIBUTE_DIRECTORY)&&!(a&FILE_ATTRIBUTE_REPARSE_POINT);}
static int exists(const wchar_t *p){return GetFileAttributesW(p)!=INVALID_FILE_ATTRIBUTES;}
static int path(wchar_t *dst,const wchar_t *base,const wchar_t *name){return swprintf_s(dst,32768,L"%s\\%s",base,name)>=0;}
static void note(const char *s){wchar_t p[32768];FILE *f=NULL;if(path(p,job,L"update-result.txt")&&!_wfopen_s(&f,p,L"wb")&&f){fwrite(s,1,strlen(s),f);fclose(f);}}
static int launch(PROCESS_INFORMATION *pi){wchar_t exe[32768],cmd[32768];STARTUPINFOW si={0};si.cb=sizeof(si);if(!path(exe,root,L"僵尸痒痒鼠.exe"))return 0;if(swprintf_s(cmd,32768,L"\"%s\"",exe)<0)return 0;return CreateProcessW(exe,cmd,NULL,NULL,FALSE,0,NULL,root,&si,pi);}
static int restore(void){wchar_t currentData[32768],oldData[32768];path(currentData,root,L"data");path(oldData,backup,L"data");if(exists(root)){if(exists(currentData)&&!exists(oldData)&&!MoveFileW(currentData,oldData))return 0;if(!MoveFileW(root,failed))return 0;}return MoveFileW(backup,root)!=0;}
static int healthy(void){wchar_t p[32768];char b[8193];FILE *f=NULL;path(p,root,L"desktop-health.json");if(_wfopen_s(&f,p,L"rb")||!f)return 0;size_t n=fread(b,1,8192,f);fclose(f);b[n]=0;return strstr(b,"\"connected\": true")!=NULL||strstr(b,"\"connected\":true")!=NULL;}
int WINAPI wWinMain(HINSTANCE a,HINSTANCE b,LPWSTR c,int d){
 (void)a;(void)b;(void)c;(void)d;int argc=0;wchar_t **argv=CommandLineToArgvW(GetCommandLineW(),&argc);if(!argv||argc!=4)return 2;
 DWORD n=GetModuleFileNameW(NULL,job,32768);if(!n||n>=32768)return 2;wchar_t *slash=wcsrchr(job,L'\\');if(!slash)return 2;*slash=0;
 wchar_t parent[32768],rootParent[32768],brand[32768],data[32768],newData[32768];wcscpy_s(parent,32768,job);slash=wcsrchr(parent,L'\\');if(!slash||wcsncmp(slash+1,L".JiangshiYys-update-",wcslen(L".JiangshiYys-update-"))!=0)return 2;*slash=0;
 n=GetFullPathNameW(argv[1],32768,root,NULL);if(!n||n>=32768)return 2;wcscpy_s(rootParent,32768,root);slash=wcsrchr(rootParent,L'\\');if(!slash||!slash[1])return 2;*slash=0;if(_wcsicmp(parent,rootParent)!=0)return 2;
 path(fresh,job,L"new");path(backup,job,L"backup");path(failed,job,L"failed");path(brand,root,L"brand.json");path(data,root,L"data");path(newData,fresh,L"data");
 if(!plain(job)||!plain(root)||!plain(fresh)||!exists(brand)||exists(backup)||exists(failed)||exists(newData)||(exists(data)&&!plain(data)))return 2;
 DWORD pid=(DWORD)wcstoul(argv[2],NULL,10);ULONGLONG expected=_wcstoui64(argv[3],NULL,10);HANDLE process=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);FILETIME ct,et,kt,ut;ULARGE_INTEGER stamp;
 if(!process||!GetProcessTimes(process,&ct,&et,&kt,&ut))return 3;stamp.LowPart=ct.dwLowDateTime;stamp.HighPart=ct.dwHighDateTime;if(stamp.QuadPart!=expected){CloseHandle(process);return 3;}
 DWORD waited=WaitForSingleObject(process,60000);CloseHandle(process);if(waited!=WAIT_OBJECT_0){note("Old launcher did not exit; installation was not changed.");return 4;}
 int moved=0;for(int i=0;i<40;i++){if(MoveFileW(root,backup)){moved=1;break;}Sleep(500);}if(!moved){note("Cannot move old installation. No files replaced.");goto oldstart;}
 if(!MoveFileW(fresh,root)){MoveFileW(backup,root);note("Cannot activate new installation; old directory restored.");goto oldstart;}
 wchar_t dest[32768],oldData[32768];path(dest,root,L"data");path(oldData,backup,L"data");if(exists(oldData)&&!MoveFileW(oldData,dest)){restore();note("Cannot transfer data; rollback attempted. Backups retained.");goto oldstart;}
 PROCESS_INFORMATION pi={0};if(!launch(&pi)){restore();note("New launcher could not start; rollback attempted.");goto oldstart;}CloseHandle(pi.hThread);
 for(int i=0;i<90;i++){if(healthy()){CloseHandle(pi.hProcess);note("Update complete. Previous installation retained in backup; user data moved without copying or deletion.");return 0;}if(WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0){CloseHandle(pi.hProcess);if(restore()){note("New launcher exited before ready; old version restored.");goto oldstart;}note("Rollback could not complete; backup retained.");return 5;}Sleep(500);}
 CloseHandle(pi.hProcess);note("New launcher started; readiness not confirmed within 45 seconds. Current data and backup retained.");return 0;
 oldstart: {PROCESS_INFORMATION old={0};if(launch(&old)){CloseHandle(old.hThread);CloseHandle(old.hProcess);}MessageBoxW(NULL,L"自动更新未完成，已尝试恢复旧版本。旧文件保留在更新备份目录，请查看 update-result.txt。",L"软件更新",MB_OK|MB_ICONWARNING);return 6;}
}
