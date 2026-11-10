/* Synthetic no-window process for installer tests only. */
#include <windows.h>
#include <stdio.h>
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){
 (void)a;(void)b;(void)c;(void)d;
 if(GetFileAttributesW(L"fail-start.txt")!=INVALID_FILE_ATTRIBUTES)return 1;
 FILE *f=NULL;fopen_s(&f,"desktop-health.json","wb");
 if(f){fputs("{\"connected\":true}",f);fclose(f);}return 0;
}
