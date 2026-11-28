from pathlib import Path
import json
p=Path(__file__).resolve().parent
c=(p/'shop_agent.c').read_text(encoding='utf-8')
a=c.index(' if(*(DWORD*)param==64)') if ' if(*(DWORD*)param==64)' in c else c.index(' snprintf(')
b=c.index('\n int gil=',a)
def embed(name):
 script=(p/name).read_text(encoding='utf-8')
 return 'snprintf(code,sizeof(code),"f=open(r\'%s\',\'wb\',0)\\n%s",pipe,'+json.dumps(script,ensure_ascii=True)+');'
c=c[:a]+' if(*(DWORD*)param==64){'+embed('bond_read.py')+'}else if(*(DWORD*)param==128){'+embed('identity_read.py')+'}else{'+embed('shop_read.py')+'}'+c[b:]
(p/'shop_agent.c').write_text(c,encoding='utf-8')
