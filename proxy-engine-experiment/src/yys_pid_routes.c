#include "pb_internal.h"

// No process-name wildcard rules: each registration owns a verified process handle.
typedef struct { DWORD pid; UINT64 stamp; UINT32 config; HANDLE process; } YYS_ROUTE;
static YYS_ROUTE yys_routes[64];
volatile BOOL g_yys_has_routes = FALSE;
static SRWLOCK yys_route_lock = SRWLOCK_INIT;
static HANDLE yys_job = NULL;
static UINT32 yys_job_config = 0;

static UINT64 yys_stamp(HANDLE process) {
    FILETIME created, exited, kernel, user;
    if (!GetProcessTimes(process, &created, &exited, &kernel, &user)) return 0;
    return ((UINT64)created.dwHighDateTime << 32) | created.dwLowDateTime;
}

PROXYBRIDGE_API BOOL Yys_SetPidRoute(DWORD pid, UINT64 stamp, UINT32 config) {
    if (pid == 0 || stamp == 0 || config == 0 || pid == GetCurrentProcessId()) return FALSE;
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, pid);
    if (!process) return FALSE;
    if (yys_stamp(process) != stamp || WaitForSingleObject(process, 0) != WAIT_TIMEOUT) {
        CloseHandle(process); return FALSE;
    }
    AcquireSRWLockExclusive(&yys_route_lock);
    int index = -1;
    for (int i = 0; i < 64; ++i) if (yys_routes[i].pid == pid) { index = i; break; }
    if (index < 0) for (int i = 0; i < 64; ++i) if (yys_routes[i].pid == 0) { index = i; break; }
    if (index >= 0) {
        if (yys_routes[index].process) CloseHandle(yys_routes[index].process);
        yys_routes[index].pid = pid; yys_routes[index].stamp = stamp;
        yys_routes[index].config = config; yys_routes[index].process = process;
        g_yys_has_routes = TRUE;
    }
    ReleaseSRWLockExclusive(&yys_route_lock);
    if (index < 0) CloseHandle(process);
    return index >= 0;
}

PROXYBRIDGE_API BOOL Yys_RemovePidRoute(DWORD pid) {
    BOOL found = FALSE;
    AcquireSRWLockExclusive(&yys_route_lock);
    for (int i = 0; i < 64; ++i) if (yys_routes[i].pid == pid) {
        if (yys_routes[i].process) CloseHandle(yys_routes[i].process);
        ZeroMemory(&yys_routes[i], sizeof(YYS_ROUTE)); found = TRUE;
    }
    g_yys_has_routes = (yys_job != NULL);
    for (int i = 0; i < 64; ++i) if (yys_routes[i].pid != 0) { g_yys_has_routes = TRUE; break; }
    ReleaseSRWLockExclusive(&yys_route_lock);
    return found;
}

// One private job per broker. Windows assigns ordinary descendants before they run;
// matching membership at connection time avoids a polling-only child discovery gap.
PROXYBRIDGE_API BOOL Yys_SetJobRoute(HANDLE job, DWORD root, UINT32 config) {
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, root);
    BOOL member = FALSE;
    if (!process) return FALSE;
    BOOL valid = IsProcessInJob(process, job, &member);
    CloseHandle(process);
    if (!valid || !member || !config) return FALSE;
    HANDLE copy = NULL;
    if (!DuplicateHandle(GetCurrentProcess(), job, GetCurrentProcess(), &copy, 0, FALSE, DUPLICATE_SAME_ACCESS)) return FALSE;
    AcquireSRWLockExclusive(&yys_route_lock);
    if (yys_job) CloseHandle(yys_job);
    yys_job = copy; yys_job_config = config; g_yys_has_routes = TRUE;
    ReleaseSRWLockExclusive(&yys_route_lock);
    return TRUE;
}
PROXYBRIDGE_API void Yys_ClearJobRoute(void) {
    AcquireSRWLockExclusive(&yys_route_lock);
    if (yys_job) CloseHandle(yys_job);
    yys_job = NULL; yys_job_config = 0;
    g_yys_has_routes = FALSE;
    for (int i=0;i<64;i++) if (yys_routes[i].pid) {g_yys_has_routes=TRUE;break;}
    ReleaseSRWLockExclusive(&yys_route_lock);
}
static BOOL yys_job_member(DWORD pid) {
    if (!yys_job || !pid) return FALSE;
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!process) return FALSE;
    BOOL member = FALSE;
    BOOL ok = IsProcessInJob(process, yys_job, &member);
    CloseHandle(process);
    return ok && member;
}
PROXYBRIDGE_API BOOL Yys_IsJobMember(DWORD pid) {
    AcquireSRWLockShared(&yys_route_lock);
    BOOL member = yys_job_member(pid);
    ReleaseSRWLockShared(&yys_route_lock);
    return member;
}

// -1 means unmanaged: leave the upstream handling unchanged. Managed TCP is
// proxied; managed UDP/IPv6 or an invalid/missing config is BLOCKED in this pilot.
PROXYBRIDGE_API int Yys_MatchPidRoute(DWORD pid, BOOL udp, BOOL ipv6, UINT32 *config) {
    if (pid == 0) return -1;
    int action = -1;
    AcquireSRWLockShared(&yys_route_lock);
    for (int i = 0; i < 64; ++i) if (yys_routes[i].pid == pid) {
        YYS_ROUTE *route = &yys_routes[i];
        action = RULE_ACTION_BLOCK;
        if (!udp && !ipv6 && WaitForSingleObject(route->process, 0) == WAIT_TIMEOUT && yys_stamp(route->process) == route->stamp) {
            PROXY_CONFIG *proxy = find_proxy_config(route->config);
            if (proxy && proxy->config_id == route->config && proxy->type == PROXY_TYPE_SOCKS5 && proxy->host[0] && proxy->port) {
                if (config) *config = route->config;
                action = RULE_ACTION_PROXY;
            }
        }
        break;
    }
    if (action < 0 && yys_job_member(pid)) {
        action = RULE_ACTION_BLOCK;
        PROXY_CONFIG *proxy = find_proxy_config(yys_job_config);
        if (!udp && !ipv6 && proxy && proxy->config_id == yys_job_config &&
            proxy->type == PROXY_TYPE_SOCKS5 && proxy->host[0] && proxy->port) {
            if (config) *config = yys_job_config;
            action = RULE_ACTION_PROXY;
        }
    }
    ReleaseSRWLockShared(&yys_route_lock);
    return action;
}


// Keep the same capture file object alive in the independent controller. If
// this broker is terminated, capture remains active until the controller first
// stops its owned game and then closes the pinned handle.
PROXYBRIDGE_API BOOL Yys_PinCapture(DWORD guard_pid, UINT64 guard_stamp, UINT64 *out_handle) {
    if (!out_handle || !running || windivert_handle == INVALID_HANDLE_VALUE || guard_pid == GetCurrentProcessId()) return FALSE;
    HANDLE guard = OpenProcess(PROCESS_DUP_HANDLE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, guard_pid);
    if (!guard) return FALSE;
    if (yys_stamp(guard) != guard_stamp || WaitForSingleObject(guard, 0) != WAIT_TIMEOUT) { CloseHandle(guard); return FALSE; }
    HANDLE copy = NULL;
    BOOL ok = DuplicateHandle(GetCurrentProcess(), windivert_handle, guard, &copy, 0, FALSE, DUPLICATE_SAME_ACCESS);
    CloseHandle(guard);
    if (ok) *out_handle = (UINT64)(ULONG_PTR)copy;
    return ok;
}
