from pathlib import Path
import json
p=Path(__file__).resolve().parent
c=p.joinpath('shop_agent.c').read_text('utf-8')
a=c.index('snprintf(');b=c.index('\n int gil=',a)
s=p.joinpath('shop_read.py').read_text('utf-8')
c=c[:a]+'snprintf(code,sizeof(code),"f=open(r\'%s\',\'wb\',0)\\n%s",pipe,'+json.dumps(s,ensure_ascii=True)+');'+c[b:]
p.joinpath('shop_agent.c').write_text(c,'utf-8')
