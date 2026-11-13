from pathlib import Path
import re,json,html,datetime,sys
ROOT=Path(__file__).resolve().parent.parent;OUT=ROOT/'research/official-server-merges'
servers=json.loads((ROOT/'servers.json').read_text('utf-8'))['servers'];names={}
for row in servers:
 for name in {row['name'],re.sub(r'^(网易|B站)-','',row['name'])}:names.setdefault(name,set()).add(str(row['id']))
links=json.loads((OUT/'index.json').read_text('utf-8'));links.setdefault('https://yys.163.com/news/update/20180113/23024_735114.html','《阴阳师》手游部分服务器合并公告')
groups={};unresolved=[];notices=[]
for url,title in sorted(links.items()):
 file=OUT/url.rsplit('/',1)[-1]
 if not file.exists():continue
 raw=file.read_text('utf-8');a=raw.find('<h1>');b=raw.find('<!--分页-->',a);raw=raw[a:b if b>a else len(raw)]
 text=html.unescape(re.sub(r'</(?:p|div|tr|li|h[1-6])>|<br\s*/?>','\n',raw,flags=re.I));text=re.sub('<[^>]*>','',text)
 m=re.search('互通服务器名单',text);old=False
 if not m:m=re.search('合服列表如下',text);old=True
 if not m:
  channel=re.search(r'部分渠道服务器[（(]([^）)]+)[）)]进行合并',text)
  if channel:
   text='合服列表如下\n'+channel.group(1)+'\n注意事项';m=re.search('合服列表如下',text);old=True
 if not m:continue
 end=re.search('更多服务器|注意事项|预计时间',text[m.end():]);section=text[m.end():m.end()+end.start() if end else len(text)]
 notice_groups=[]
 for line in section.splitlines():
  line=line.strip()
  if not line:continue
  listed=re.findall('「([^」]+)」',line) if not old else [x.strip() for x in re.split('[，,、]',line)]
  if len(listed)<2:continue
  ids=[];missing=[]
  for name in listed:
   found=names.get(name,set())
   if len(found)!=1:missing.append(name)
   else:ids.append(next(iter(found)))
  if missing:unresolved.append({'url':url,'names':listed,'unresolved':missing});continue
  ids=sorted(set(ids),key=int)
  if len(ids)<2:continue
  key=','.join(ids);source={'url':url,'title':title,'published':re.search(r'/(\d{8})/',url).group(1)}
  group=groups.setdefault(key,{'server_ids':ids,'names':[next(r['name'] for r in servers if str(r['id'])==i) for i in ids],'sources':[]})
  if source not in group['sources']:group['sources'].append(source)
  notice_groups.append(ids)
 if notice_groups:notices.append({'url':url,'groups':notice_groups})
value={'version':1,'checked_on':'2026-11-13','index':'https://yys.163.com/news/update/','catalog_servers':len(servers),'groups':list(groups.values()),'unresolved':unresolved}
(ROOT/'server-merges.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
print('groups',len(groups),'covered server IDs',len({s for g in groups.values() for s in g['server_ids']}),'unresolved groups',len(unresolved))
for g in groups.values():print(' / '.join(g['names']))
if unresolved:print('UNRESOLVED',json.dumps(unresolved,ensure_ascii=False))
