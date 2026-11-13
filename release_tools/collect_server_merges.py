from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import urllib.request,re,json,html,time
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'research'/'official-server-merges';OUT.mkdir(parents=True,exist_ok=True)
def fetch(url):
 name=url.rsplit('/',1)[-1] or 'index.html';target=OUT/name
 if target.exists():return target.read_text('utf-8')
 request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
 for attempt in range(2):
  try:
   data=urllib.request.urlopen(request,timeout=18).read().decode('utf-8','replace');target.write_text(data,'utf-8');return data
  except Exception:
   if attempt:raise
   time.sleep(1)
def plain(s):
 s=re.sub(r'<(?:script|style)\b.*?</(?:script|style)>','',s,flags=re.S|re.I)
 s=re.sub(r'</(?:p|div|tr|li|h[1-6])>|<br\s*/?>','\n',s,flags=re.I)
 return html.unescape(re.sub('<[^>]*>','',s))
links={};errors=[]
urls=['https://yys.163.com/news/update/'+('' if i==1 else 'index_'+str(i)+'.html') for i in range(1,50)]
with ThreadPoolExecutor(max_workers=6) as pool:
 jobs={pool.submit(fetch,u):u for u in urls}
 for job in as_completed(jobs):
  try:
   for url,title in re.findall(r'<a class="link" href="([^"]+)"[^>]*title="([^"]+)"',job.result()):
    if any(w in title for w in ('维护','合并','互通','合服')):links['https:'+url if url.startswith('//') else url]=title
  except Exception as e:errors.append({'url':jobs[job],'error':str(e)})
print('Official index pages:',len(urls)-len(errors),'candidate notices:',len(links),flush=True)
(OUT/'index.json').write_text(json.dumps(links,ensure_ascii=False,indent=2),'utf-8')
matched=[];done=0
with ThreadPoolExecutor(max_workers=6) as pool:
 jobs={pool.submit(fetch,u):u for u in links}
 for job in as_completed(jobs):
  done+=1;url=jobs[job]
  try:
   raw=job.result();text=plain(raw)
   # Capture actual announcement body, not sidebar recommendations.
   start=raw.find('<h1>');end=raw.find('<!--分页-->',start)
   body=raw[start:end if end>start else len(raw)];text=plain(body)
   patterns=list(re.finditer('服务器数据互通|服务器合并|合服列表',text))
   if patterns:
    sections=[]
    for match in patterns:
     begin=max(0,match.start()-30);stop=text.find('※注意事项',match.end())
     if stop<0 or stop>match.start()+6500:stop=min(len(text),match.start()+6500)
     sections.append(text[begin:stop])
    matched.append({'url':url,'title':links[url],'sections':sections,'images':re.findall(r'<img[^>]+src="([^"]+)"',body)})
  except Exception as e:errors.append({'url':url,'error':str(e)})
  if done%50==0:print('Checked',done,'/',len(links),'matched',len(matched),flush=True)
(OUT/'announcements.json').write_text(json.dumps(matched,ensure_ascii=False,indent=2),'utf-8')
(OUT/'errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),'utf-8')
print('Complete:',len(matched),'notices, errors:',len(errors),flush=True)
