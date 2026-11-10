#include "pb_internal.h"
#define YYS_DNS_MAX 4096
#define YYS_DNS_PENDING 64
typedef void (*YYS_DNS_CALLBACK)(UINT64, DWORD, const UINT8 *, UINT);
typedef struct { UINT64 token; ULONGLONG expires; UINT hlen; UINT8 header[68]; UINT8 id[2]; WINDIVERT_ADDRESS addr; } YYS_DNS_REQUEST;
static YYS_DNS_CALLBACK yys_dns_callback = NULL;
static YYS_DNS_REQUEST yys_dns_pending[YYS_DNS_PENDING];
static SRWLOCK yys_dns_lock = SRWLOCK_INIT;
static volatile LONG64 yys_dns_sequence = 0;
static volatile LONG yys_dns_seen = 0, yys_dns_outbound = 0, yys_dns_managed = 0;
static volatile DWORD yys_dns_last_owner = 0;
PROXYBRIDGE_API void Yys_GetDnsDebug(UINT32 *out) { if (out) {out[0]=yys_dns_seen;out[1]=yys_dns_outbound;out[2]=yys_dns_managed;out[3]=yys_dns_last_owner;} }

PROXYBRIDGE_API void Yys_SetDnsCallback(YYS_DNS_CALLBACK cb) { yys_dns_callback = cb; }
PROXYBRIDGE_API void Yys_ClearDns(void) {
    AcquireSRWLockExclusive(&yys_dns_lock);
    ZeroMemory(yys_dns_pending, sizeof(yys_dns_pending));
    ReleaseSRWLockExclusive(&yys_dns_lock);
}
// Pure packet builder, also used by local no-driver tests.
PROXYBRIDGE_API UINT Yys_BuildDnsReply(const UINT8 *query, UINT qlen, const UINT8 *dns, UINT dlen, UINT8 *out, UINT capacity) {
    if (!query || !dns || !out || qlen < 40 || dlen < 12 || dlen > 512) return 0;
    const WINDIVERT_IPHDR *ip = (const WINDIVERT_IPHDR *)query;
    UINT ih = ip->HdrLength * 4;
    if (ip->Version != 4 || ip->Protocol != IPPROTO_UDP || ih < 20 || ih > 60 || qlen < ih+20 ||
        WINDIVERT_IPHDR_GET_FRAGOFF(ip) || WINDIVERT_IPHDR_GET_MF(ip)) return 0;
    const WINDIVERT_UDPHDR *udp = (const WINDIVERT_UDPHDR *)(query+ih);
    UINT len = ih+8+dlen;
    if (udp->DstPort != htons(53) || capacity < len || !(dns[2]&0x80) ||
        query[ih+8]!=dns[0] || query[ih+9]!=dns[1]) return 0;
    memcpy(out, query, ih+8); memcpy(out+ih+8,dns,dlen);
    WINDIVERT_IPHDR *reply = (WINDIVERT_IPHDR *)out;
    UINT32 swap=reply->SrcAddr; reply->SrcAddr=reply->DstAddr;reply->DstAddr=swap;
    reply->Length=htons((UINT16)len);reply->TTL=64;
    WINDIVERT_UDPHDR *ru=(WINDIVERT_UDPHDR *)(out+ih);
    UINT16 port=ru->SrcPort;ru->SrcPort=ru->DstPort;ru->DstPort=port;ru->Length=htons((UINT16)(8+dlen));
    return len;
}
// Called before the general UDP block path. Only known managed process-owned DNS
// is consumed; shared Windows DNS Client service traffic remains outside scope.
BOOL yys_handle_dns(const UINT8 *packet, UINT len, const WINDIVERT_ADDRESS *addr) {
    InterlockedIncrement(&yys_dns_seen);
    if (!yys_dns_callback || !addr->Outbound || len < 40) return FALSE;
    const WINDIVERT_IPHDR *ip=(const WINDIVERT_IPHDR *)packet;
    UINT ih=ip->HdrLength*4;
    if (ip->Version!=4 || ip->Protocol!=IPPROTO_UDP || ih<20 || ih>60 || len<ih+20 ||
        WINDIVERT_IPHDR_GET_FRAGOFF(ip) || WINDIVERT_IPHDR_GET_MF(ip)) return FALSE;
    const WINDIVERT_UDPHDR *udp=(const WINDIVERT_UDPHDR *)(packet+ih);
    if (udp->DstPort!=htons(53)) return FALSE;
    InterlockedIncrement(&yys_dns_outbound);
    DWORD pid=get_process_id_from_udp_connection(ip->SrcAddr,ntohs(udp->SrcPort));
    yys_dns_last_owner=pid;
    if (Yys_MatchPidRoute(pid,TRUE,FALSE,NULL)<0) return FALSE;
    InterlockedIncrement(&yys_dns_managed);
    UINT ulen=ntohs(udp->Length);
    if (ulen<20 || ulen>8+YYS_DNS_MAX || ih+ulen>len) return TRUE;
    const UINT8 *dns=packet+ih+8;
    if (dns[2]&0x80) return TRUE;
    UINT64 token=0; ULONGLONG now=GetTickCount64();
    AcquireSRWLockExclusive(&yys_dns_lock);
    for (int i=0;i<YYS_DNS_PENDING;i++) if (!yys_dns_pending[i].token || yys_dns_pending[i].expires<now) {
        YYS_DNS_REQUEST *p=&yys_dns_pending[i];
        token=(UINT64)InterlockedIncrement64(&yys_dns_sequence);
        p->token=token;p->expires=now+45000;p->hlen=ih+8;
        memcpy(p->header,packet,p->hlen);memcpy(p->id,dns,2);p->addr=*addr;break;
    }
    ReleaseSRWLockExclusive(&yys_dns_lock);
    if (token) yys_dns_callback(token,pid,dns,ulen-8);
    return TRUE; // queue saturation and errors drop; never pass query direct
}
PROXYBRIDGE_API BOOL Yys_CompleteDns(UINT64 token,const UINT8 *dns,UINT len) {
    YYS_DNS_REQUEST request={0};
    AcquireSRWLockExclusive(&yys_dns_lock);
    for (int i=0;i<YYS_DNS_PENDING;i++) if (yys_dns_pending[i].token==token) {
        request=yys_dns_pending[i];yys_dns_pending[i].token=0;break;
    }
    ReleaseSRWLockExclusive(&yys_dns_lock);
    if (!request.token || request.expires<GetTickCount64() || !dns || !len || !running || windivert_handle==INVALID_HANDLE_VALUE) return FALSE;
    UINT8 query[80]={0},reply[600];
    memcpy(query,request.header,request.hlen);memcpy(query+request.hlen,request.id,2);
    UINT size=Yys_BuildDnsReply(query,request.hlen+12,dns,len,reply,sizeof(reply));
    if (!size) return FALSE;
    request.addr.Outbound = request.addr.Loopback ? TRUE : FALSE;
    if (!WinDivertHelperCalcChecksums(reply,size,&request.addr,0)) return FALSE;
    return WinDivertSend(windivert_handle,reply,size,NULL,&request.addr);
}
