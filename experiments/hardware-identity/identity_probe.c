/* Self-loaded hooks restricted to explicitly marked, owned test processes.
   No remote injection, driver, registry writes, NIC changes, or game support. */
#define _WIN32_WINNT 0x0601
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <wchar.h>
#include <string.h>
#include "MinHook.h"

static BOOL (WINAPI *real_name)(LPWSTR,LPDWORD);
static BOOL (WINAPI *real_volume)(LPCWSTR,LPWSTR,DWORD,LPDWORD,LPDWORD,LPDWORD,LPWSTR,DWORD);
static ULONG (WINAPI *real_info)(PIP_ADAPTER_INFO,PULONG);
static ULONG (WINAPI *real_addresses)(ULONG,ULONG,PVOID,PIP_ADAPTER_ADDRESSES,PULONG);
static WCHAR virtual_name[16];static DWORD virtual_volume;static BYTE virtual_mac[6];
static volatile LONG counts[4];static BOOL active=FALSE;static BOOL owned_game=FALSE;

static void mac_for_index(BYTE *dest,ULONG index){
    memcpy(dest,virtual_mac,6);dest[0]=(dest[0]|2)&0xfe;
    dest[4]^=(BYTE)(index>>8);dest[5]^=(BYTE)index;
}
static BOOL WINAPI hook_name(LPWSTR buffer,LPDWORD size){
    InterlockedIncrement(&counts[0]);
    if(!size){SetLastError(ERROR_INVALID_PARAMETER);return FALSE;}
    DWORD length=(DWORD)wcslen(virtual_name);
    if(!buffer||*size<=length){*size=length+1;SetLastError(ERROR_BUFFER_OVERFLOW);return FALSE;}
    memcpy(buffer,virtual_name,(length+1)*sizeof(WCHAR));*size=length;return TRUE;
}
static BOOL WINAPI hook_volume(LPCWSTR path,LPWSTR name,DWORD name_size,LPDWORD serial,LPDWORD component,LPDWORD flags,LPWSTR fs,DWORD fs_size){
    InterlockedIncrement(&counts[1]);
    BOOL result=real_volume(path,name,name_size,serial,component,flags,fs,fs_size);
    if(result&&serial)*serial=virtual_volume;
    return result;
}
static ULONG WINAPI hook_info(PIP_ADAPTER_INFO info,PULONG size){
    InterlockedIncrement(&counts[2]);ULONG status=real_info(info,size);
    if(status==ERROR_SUCCESS){for(PIP_ADAPTER_INFO row=info;row;row=row->Next)if(row->AddressLength==6)mac_for_index(row->Address,row->Index);}
    return status;
}
static ULONG WINAPI hook_addresses(ULONG family,ULONG flags,PVOID reserved,PIP_ADAPTER_ADDRESSES info,PULONG size){
    InterlockedIncrement(&counts[3]);ULONG status=real_addresses(family,flags,reserved,info,size);
    if(status==ERROR_SUCCESS){for(PIP_ADAPTER_ADDRESSES row=info;row;row=row->Next)if(row->PhysicalAddressLength==6)mac_for_index(row->PhysicalAddress,row->IfIndex);}
    return status;
}
__declspec(dllexport) int WINAPI StartIdentityProbe(LPCWSTR name,DWORD serial,const BYTE *mac){
    if(!owned_game&&!wcsstr(GetCommandLineW(),L"--yys-owned-hardware-probe"))return ERROR_ACCESS_DENIED;
    if(active||!name||!mac||!serial||!wcslen(name)||wcslen(name)>15)return ERROR_INVALID_PARAMETER;
    for(const WCHAR *p=name;*p;p++)if(!((*p>=L'A'&&*p<=L'Z')||(*p>=L'0'&&*p<=L'9')||*p==L'-'))return ERROR_INVALID_PARAMETER;
    wcscpy_s(virtual_name,16,name);virtual_volume=serial;memcpy(virtual_mac,mac,6);memset((void*)counts,0,sizeof(counts));
    MH_STATUS status=MH_Initialize();if(status!=MH_OK)return 1000+(int)status;
    status=MH_CreateHookApi(L"kernel32.dll","GetComputerNameW",hook_name,(LPVOID*)&real_name);
    if(status==MH_OK)status=MH_CreateHookApi(L"kernel32.dll","GetVolumeInformationW",hook_volume,(LPVOID*)&real_volume);
    if(status==MH_OK)status=MH_CreateHookApi(L"iphlpapi.dll","GetAdaptersInfo",hook_info,(LPVOID*)&real_info);
    if(status==MH_OK)status=MH_CreateHookApi(L"iphlpapi.dll","GetAdaptersAddresses",hook_addresses,(LPVOID*)&real_addresses);
    if(status==MH_OK)status=MH_EnableHook(MH_ALL_HOOKS);
    if(status!=MH_OK){MH_Uninitialize();return 1000+(int)status;}
    active=TRUE;return 0;
}
__declspec(dllexport) int WINAPI StopIdentityProbe(void){
    if(!active)return 0;
    MH_STATUS status=MH_DisableHook(MH_ALL_HOOKS);if(status!=MH_OK)return 1000+(int)status;
    status=MH_Uninitialize();if(status!=MH_OK)return 1000+(int)status;
    active=FALSE;return 0;
}
typedef struct Snapshot { WCHAR name[256];DWORD volume,info_hash,addresses_hash,info_count,addresses_count; } Snapshot;
static DWORD hash_mac(DWORD hash,const BYTE *mac,ULONG length){for(ULONG i=0;i<length;i++)hash=(hash^mac[i])*16777619;return hash;}
__declspec(dllexport) int WINAPI ReadProbeSnapshot(Snapshot *out){
    if(!out)return ERROR_INVALID_PARAMETER;
    memset(out,0,sizeof(*out));DWORD size=256;
    if(!GetComputerNameW(out->name,&size))return (int)GetLastError();
    if(!GetVolumeInformationW(L"C:\\",NULL,0,&out->volume,NULL,NULL,NULL,0))return (int)GetLastError();
    ULONG bytes=0;GetAdaptersInfo(NULL,&bytes);
    if(bytes){PIP_ADAPTER_INFO rows=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,bytes);
        if(!rows)return ERROR_NOT_ENOUGH_MEMORY;
        if(GetAdaptersInfo(rows,&bytes)==ERROR_SUCCESS)for(PIP_ADAPTER_INFO p=rows;p;p=p->Next)if(p->AddressLength==6){out->info_hash=hash_mac(out->info_hash,p->Address,6);out->info_count++;}
        HeapFree(GetProcessHeap(),0,rows);
    }
    bytes=0;GetAdaptersAddresses(AF_UNSPEC,0,NULL,NULL,&bytes);
    if(bytes){PIP_ADAPTER_ADDRESSES rows=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,bytes);
        if(!rows)return ERROR_NOT_ENOUGH_MEMORY;
        if(GetAdaptersAddresses(AF_UNSPEC,0,NULL,rows,&bytes)==ERROR_SUCCESS)for(PIP_ADAPTER_ADDRESSES p=rows;p;p=p->Next)if(p->PhysicalAddressLength==6){out->addresses_hash=hash_mac(out->addresses_hash,p->PhysicalAddress,6);out->addresses_count++;}
        HeapFree(GetProcessHeap(),0,rows);
    }
    return 0;
}
__declspec(dllexport) void WINAPI ReadProbeCounters(DWORD *out){if(out)for(int i=0;i<4;i++)out[i]=(DWORD)counts[i];}

/* Explicit one-process handshake used only by the owned-game test controller. */
typedef struct GameContext {
    DWORD magic,pid;ULONGLONG stamp;WCHAR mutex_name[160];WCHAR name[16];DWORD serial;BYTE mac[6];DWORD counters[4];DWORD is_active;
} GameContext;
__declspec(dllexport) DWORD WINAPI StartOwnedGameTest(GameContext *ctx){
    if(!ctx||ctx->magic!=0x59595331||ctx->pid!=GetCurrentProcessId())return ERROR_ACCESS_DENIED;
    FILETIME created,exited,kernel,user;
    if(!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user))return GetLastError();
    ULONGLONG stamp=((ULONGLONG)created.dwHighDateTime<<32)|created.dwLowDateTime;
    if(stamp!=ctx->stamp||wcsncmp(ctx->mutex_name,L"Local\\YysOwnedHardware-",23))return ERROR_ACCESS_DENIED;
    HANDLE gate=OpenMutexW(SYNCHRONIZE,FALSE,ctx->mutex_name);if(!gate)return ERROR_ACCESS_DENIED;
    CloseHandle(gate);
    WCHAR exe[32768];if(!GetModuleFileNameW(NULL,exe,32768))return GetLastError();
    WCHAR *name=wcsrchr(exe,L'\\');name=name?name+1:exe;
    if(_wcsicmp(name,L"onmyoji.exe")&&_wcsicmp(name,L"onmyoji_future.exe"))return ERROR_ACCESS_DENIED;
    owned_game=TRUE;DWORD status=(DWORD)StartIdentityProbe(ctx->name,ctx->serial,ctx->mac);
    if(status)owned_game=FALSE;return status;
}
__declspec(dllexport) DWORD WINAPI OwnedGameTestStatus(GameContext *ctx){
    if(!ctx||ctx->magic!=0x59595331||ctx->pid!=GetCurrentProcessId())return ERROR_ACCESS_DENIED;
    ReadProbeCounters(ctx->counters);ctx->is_active=active;return 0;
}
__declspec(dllexport) DWORD WINAPI StopOwnedGameTest(LPVOID unused){(void)unused;return (DWORD)StopIdentityProbe();}
