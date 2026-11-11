from pathlib import Path
import re,shutil
ROOT=Path(__file__).resolve().parents[1]
source=ROOT.parent/'yys-daigan-manager/web-v2/web/public'
out=ROOT/'frontend/src/blue';out.mkdir(exist_ok=True)
t=(source/'blue-ticket-preview.html').read_text(encoding='utf-8')
t=re.sub(r'<script src="/theme[^>]+></script><link[^>]+themes[^>]+/>','',t)
a=t.index('<header>');b=t.index('</header>',a)+len('</header>')
t=t[:a]+'<header><div><small>僵尸痒痒鼠 · 本地记录</small><h1>蓝票记录</h1></div><div class="blue-tools"><button id="blue-subjects" class="secondary">选择参与角色</button><button id="blue-refresh" class="secondary">刷新</button><button id="blue-export" class="secondary">导出</button></div></header>'+t[b:]
t=re.sub(r'<p class="preview">设计预览：.*?</p>','<p class="blue-intro">只记录你选择参与的角色；名单独立于启动方案。记录保存在本机。</p><div class="blue-tools"><label><input type="checkbox" id="blue-history-roles"> 查看退出名单的历史角色</label><span id="blue-participants"></span></div>',t)
t=re.sub(r'<label id="(?:stats-)?order-scope-label".*?</label>','',t)
t=re.sub(r'<p class="hint">正式版建议：.*?</p>','<p class="hint">0 与未记录不同；修改与撤销保留本地历史。未参与角色不计入待补或零掉落。</p>',t)
a=t.index('const names=');b=t.index('const $=id=>',a)
t=t[:a]+"const BLUE_ICONS=__BLUE_ICONS__;\nconst names=[];\nconst records=new Map();\nconst localToday=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};\n"+t[b:]
t=t.replace("selectedDate='2026-10-02',weekStart='2026-09-28'","selectedDate=localToday(),weekStart=monday(localToday())")
t=re.sub(r"function subjectMatches\(n,scope\)\{return true;\}\nfunction candidateNames\(\).*?\n", "function candidateNames(){return names.map((_,n)=>n);}\n",t)
t=t.replace("periodFrom='2026-09-17',periodTo='2026-10-03'","periodFrom=localToday().slice(0,7)+'-01',periodTo=localToday()")
t=t.replace('<label>关联订单<select disabled><option>未关联订单 · 日期试设预览</option></select></label>','')
t=t.replace('日期仅用于设计试设，不代表真实订单；当前不扣减暂停日，正式版按订单服务事件计算。','仅按所选自然日范围汇总，不推测未记录日期。')
for a,b in [('按订单服务期','自选日期范围'),('服务开始日期','开始日期'),('服务结束日期','结束日期'),('订单周期','记录范围'),('服务期外','范围外'),('服务期内','范围内'),('服务期','日期范围'),('试填记录','编辑记录'),('批量试填','批量录入'),('试填当前角色','录入当前角色'),('应用到当前预览','保存记录'),('这里只应用到当前预览，不会保存到数据库。','记录保存到本机。')]:t=t.replace(a,b)
t=t.replace("if(new URLSearchParams(location.search).get('live')!=='1')render();",'// Initialize after reading the local ledger.')
t=re.sub(r"<script>const liveAdapter=.*?</script>",'<script>__DESKTOP_BLUE_ADAPTER__</script>',t,flags=re.S)
t=t.replace('src="${asset}-icon.png"','src="${BLUE_ICONS[asset]}"').replace('src="${fragment?\'black-fragment\':\'black-egg\'}-icon.png"','src="${fragment?BLUE_ICONS[\'black-fragment\']:BLUE_ICONS[\'black-egg\']}"')
t=re.sub(r'<title>.*?</title>','<title>蓝票记录 · 僵尸痒痒鼠</title>',t)
t=t.replace('订单','角色').replace('试填','录入').replace("window.addEventListener('hashchange',render);",'')
a=t.index("$('entry-form').onsubmit=e=>");b=t.index('// Initialize',a);t=t[:a]+t[b:]
t=t.replace('const size=20;', 'let size=8;')
a=t.index('function renderStatsDetails');b=t.index('function shiftDate',a);part=t[a:b].replace('/20','/blueTablePageSize').replace('*20','*blueTablePageSize').replace('每页 20 项','每页 ${blueTablePageSize} 项');t=t[:a]+part+t[b:]
t=t.replace('[6,10,20,50].map(value=>','[weekPageSize].map(value=>')
css='body{margin:0;background:#f6f2e8;font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif}main{max-width:none;padding:20px}main>header{align-items:center}.blue-tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.blue-intro,.blue-tools label{font-size:12px;color:#8a7966}.blue-tools input[type=checkbox]{width:auto}.panel{margin-top:15px}.status{white-space:pre-wrap}.blue-roles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px;max-height:55vh;overflow:auto;padding:8px}.blue-roles label{display:flex;gap:8px;border:1px solid #e5d8c5;padding:10px;border-radius:6px}.blue-roles input{width:auto}.blue-roles small{display:block;color:#8c7b69}.history-button{font-size:11px;padding:3px 7px;margin:4px 0 0}.blue-export-preview{max-width:100%;max-height:45vh;object-fit:contain}dialog{max-height:88vh;overflow:auto}.blue-export-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.blue-error{color:#a74130}.blue-empty{padding:50px 20px;text-align:center;color:#8a7966}.blue-save-busy{opacity:.65;pointer-events:none}'
t=t.replace('</style>','</style><style>'+css+'</style><style>__DESKTOP_BLUE_STYLES__</style>',1)
assert '订单' not in t and 'blue-ticket-live.js' not in t and 'const source=[' not in t and 'const BLUE_ICONS=' in t
(out/'workspace.html').write_text(t,encoding='utf-8')
for n in ['blue-ticket-icon.png','black-fragment-icon.png','black-egg-icon.png']:shutil.copy2(source/n,out/n)
print('Role-only local workspace generated; website read-only.')
