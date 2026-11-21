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
/* Journal top-level moves so a partial replacement can be reversed. */
#define ENTRY_LIMIT 4096
static wchar_t oldNames[ENTRY_LIMIT][MAX_PATH],newNames[ENTRY_LIMIT][MAX_PATH];
static int oldCount,newCount,oldMoved,newMoved;
static int reserved(const wchar_t *name){return !_wcsicmp(name,L"data")||!_wcsicmp(name,L"_updates")||!_wcsicmp(name,L"update-downloads");}
static int inventory(const wchar_t *base,wchar_t names[][MAX_PATH],int *count,int incoming){
 wchar_t pattern[32768];WIN32_FIND_DATAW entry;*count=0;
 if(!path(pattern,base,L"*"))return 0;
 HANDLE search=FindFirstFileW(pattern,&entry);if(search==INVALID_HANDLE_VALUE)return 0;
 do{
  if(!wcscmp(entry.cFileName,L".")||!wcscmp(entry.cFileName,L".."))continue;
  if(reserved(entry.cFileName)){if(incoming){FindClose(search);return 0;}continue;}
  if(*count>=ENTRY_LIMIT||wcslen(entry.cFileName)>=MAX_PATH){FindClose(search);return 0;}
  wcscpy_s(names[(*count)++],MAX_PATH,entry.cFileName);
 }while(FindNextFileW(search,&entry));
 DWORD error=GetLastError();FindClose(search);return error==ERROR_NO_MORE_FILES;
}
static int move_entry(const wchar_t *from,const wchar_t *to,const wchar_t *name){
 wchar_t source[32768],target[32768];if(!path(source,from,name)||!path(target,to,name))return 0;
 for(int retry=0;retry<40;retry++){if(MoveFileW(source,target))return 1;Sleep(250);}return 0;
}
static int restore(void){
 if(newMoved&&!exists(failed)&&!CreateDirectoryW(failed,NULL))return 0;
 for(int i=newMoved-1;i>=0;i--)if(!move_entry(root,failed,newNames[i]))return 0;
 newMoved=0;
 for(int i=oldMoved-1;i>=0;i--)if(!move_entry(backup,root,oldNames[i]))return 0;
 oldMoved=0;return 1;
}
static int healthy(void){wchar_t p[32768];char b[8193];FILE *f=NULL;path(p,root,L"desktop-health.json");if(_wfopen_s(&f,p,L"rb")||!f)return 0;size_t n=fread(b,1,8192,f);fclose(f);b[n]=0;return strstr(b,"\"connected\": true")!=NULL||strstr(b,"\"connected\":true")!=NULL;}
int WINAPI wWinMain(HINSTANCE a,HINSTANCE b,LPWSTR c,int d){
 (void)a;(void)b;(void)c;(void)d;int argc=0;wchar_t **argv=CommandLineToArgvW(GetCommandLineW(),&argc);if(!argv||argc!=4)return 2;
 DWORD n=GetModuleFileNameW(NULL,job,32768);if(!n||n>=32768)return 2;wchar_t *slash=wcsrchr(job,L'\\');if(!slash)return 2;*slash=0;
 wchar_t workspace[32768],parent[32768],brand[32768],data[32768],newData[32768];
 wcscpy_s(workspace,32768,job);slash=wcsrchr(workspace,L'\\');if(!slash||wcsncmp(slash+1,L"job-",4))return 2;*slash=0;
 wcscpy_s(parent,32768,workspace);slash=wcsrchr(parent,L'\\');if(!slash||_wcsicmp(slash+1,L"_updates"))return 2;*slash=0;
 n=GetFullPathNameW(argv[1],32768,root,NULL);if(!n||n>=32768||_wcsicmp(parent,root))return 2;
 path(fresh,job,L"new");path(backup,job,L"backup");path(failed,job,L"failed");path(brand,root,L"brand.json");path(data,root,L"data");path(newData,fresh,L"data");
 if(!plain(workspace)||!plain(job)||!plain(root)||!plain(fresh)||!exists(brand)||exists(backup)||exists(failed)||exists(newData)||(exists(data)&&!plain(data)))return 2;
 if(!inventory(root,oldNames,&oldCount,0)||!inventory(fresh,newNames,&newCount,1))return 2;
 DWORD pid=(DWORD)wcstoul(argv[2],NULL,10);ULONGLONG expected=_wcstoui64(argv[3],NULL,10);HANDLE process=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);FILETIME ct,et,kt,ut;ULARGE_INTEGER stamp;
 if(!process||!GetProcessTimes(process,&ct,&et,&kt,&ut))return 3;stamp.LowPart=ct.dwLowDateTime;stamp.HighPart=ct.dwHighDateTime;if(stamp.QuadPart!=expected){CloseHandle(process);return 3;}
 DWORD waited=WaitForSingleObject(process,60000);CloseHandle(process);if(waited!=WAIT_OBJECT_0){note("Old launcher did not exit; installation was not changed.");return 4;}
 if(!CreateDirectoryW(backup,NULL)){note("Cannot create internal backup directory.");goto oldstart;}
 for(int i=0;i<oldCount;i++){
  if(!move_entry(root,backup,oldNames[i])){restore();note("Cannot back up installation; rollback attempted.");goto oldstart;}
  oldMoved++;
 }
 for(int i=0;i<newCount;i++){
  if(!move_entry(fresh,root,newNames[i])){restore();note("Cannot install new files; rollback attempted.");goto oldstart;}
  newMoved++;
 }
 PROCESS_INFORMATION pi={0};if(!launch(&pi)){restore();note("New launcher could not start; rollback attempted.");goto oldstart;}CloseHandle(pi.hThread);
 for(int i=0;i<90;i++){if(healthy()){CloseHandle(pi.hProcess);note("Update complete. Previous installation retained in backup; user data kept in its original directory.");return 0;}if(WaitForSingleObject(pi.hProcess,0)==WAIT_OBJECT_0){CloseHandle(pi.hProcess);if(restore()){note("New launcher exited before ready; old version restored.");goto oldstart;}note("Rollback could not complete; backup retained.");return 5;}Sleep(500);}
 CloseHandle(pi.hProcess);note("New launcher started; readiness not confirmed within 45 seconds. Current data and backup retained.");return 0;
 oldstart: {PROCESS_INFORMATION old={0};if(launch(&old)){CloseHandle(old.hThread);CloseHandle(old.hProcess);}MessageBoxW(NULL,L"自动更新未完成，已尝试恢复旧版本。旧文件保留在更新备份目录，请查看 update-result.txt。",L"软件更新",MB_OK|MB_ICONWARNING);return 6;}
}
