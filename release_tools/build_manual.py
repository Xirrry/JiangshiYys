"""Render the same trusted manual into app content and standalone offline HTML."""
from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parents[1]
CSS = '''.manual-content{color:#514538;font-size:14px;line-height:1.85;overflow-wrap:anywhere}
.manual-content h1{font-size:24px;margin:0 0 12px}.manual-content h2{font-size:20px;margin:30px 0 12px;padding-top:12px;border-top:1px solid #e6dbca;scroll-margin-top:12px}.manual-content h3{font-size:16px;margin:22px 0 8px;scroll-margin-top:12px}
.manual-content p{margin:10px 0}.manual-content ul,.manual-content ol{padding-left:25px;margin:10px 0}.manual-content li{margin:6px 0}.manual-content code{font-family:Consolas,"Microsoft YaHei UI",monospace;font-size:.93em;background:#eee6da;border-radius:3px;padding:2px 5px;white-space:normal}
.manual-content a{color:#8c4a2d;text-decoration:underline;text-underline-offset:3px}.manual-content table{width:100%;border-collapse:collapse;font-size:13px;margin:14px 0}.manual-content th,.manual-content td{border:1px solid #ded0bc;text-align:left;padding:9px 11px;vertical-align:top}.manual-content th{background:#eee5d4}.manual-content td:first-child{min-width:120px}
.manual-content .manual-toc{background:#f2eadf;border:1px solid #e2d4c1;border-radius:7px;padding:15px 20px;margin:18px 0}.manual-content .manual-toc ol{list-style:none;padding-left:0;columns:2;column-gap:35px}.manual-content .manual-toc li{break-inside:avoid}.manual-content .manual-top{display:inline-block;font-size:12px;margin-bottom:4px}
@media(max-width:650px){.manual-content .manual-toc ol{columns:1}.manual-content table{font-size:12px}.manual-content td,.manual-content th{padding:6px}}
@media print{.manual-content .manual-toc ol{columns:2}.manual-content a{color:inherit}.manual-content h2,.manual-content h3{break-after:avoid}.manual-content tr{break-inside:avoid}}
'''

def inline(text):
    chunks=re.split(r'(`[^`]+`)',text)
    for i,chunk in enumerate(chunks):
        if chunk.startswith('`') and chunk.endswith('`'):
            chunks[i]='<code>'+html.escape(chunk[1:-1])+'</code>'
        else:
            chunks[i]=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',html.escape(chunk))
    return ''.join(chunks)

def render(source):
    lines=source.splitlines();body=[];toc=[];i=0;section=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        heading=re.match(r'^(#{1,3}) (.+)',line)
        if heading:
            level=len(heading[1]);title=heading[2]
            if level==1:
                body.append('<h1 id="manual-top">'+inline(title)+'</h1>')
                body.append('<!--TOC-->')
            elif level==2:
                section+=1;anchor=f'manual-section-{section}';toc.append((anchor,title))
                body.append(f'<h2 id="{anchor}">{inline(title)}</h2><a class="manual-top" href="#manual-top">返回目录 ↑</a>')
            else:body.append('<h3>'+inline(title)+'</h3>')
            i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                cells=[c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',c) for c in cells):rows.append(cells)
                i+=1
            body.append('<table><thead><tr>'+''.join('<th>'+inline(c)+'</th>' for c in rows[0])+'</tr></thead><tbody>')
            for row in rows[1:]:body.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>')
            body.append('</tbody></table>');continue
        match=re.match(r'^(?:\d+\. |[-] )(.+)',line)
        if match:
            ordered=bool(re.match(r'^\d+\.',line));tag='ol' if ordered else 'ul';body.append('<'+tag+'>')
            pattern=r'^\d+\. (.+)' if ordered else r'^- (.+)'
            while i<len(lines) and (match:=re.match(pattern,lines[i].strip())):
                body.append('<li>'+inline(match[1])+'</li>');i+=1
            body.append('</'+tag+'>');continue
        paragraph=[]
        while i<len(lines) and lines[i].strip():
            paragraph.append(lines[i].strip());i+=1
        body.append('<p>'+inline(' '.join(paragraph))+'</p>')
    nav='<nav class="manual-toc" aria-label="使用手册目录"><strong>目录 · 点击章节跳转</strong><ol>'+''.join(f'<li><a href="#{anchor}">{html.escape(title)}</a></li>' for anchor,title in toc)+'</ol></nav>'
    return '\n'.join(body).replace('<!--TOC-->',nav)

def main():
    source=(ROOT/'用户使用手册.md').read_text(encoding='utf-8');content=render(source)
    (ROOT/'frontend/src/user_manual.html').write_text(content,encoding='utf-8')
    (ROOT/'frontend/src/manual.css').write_text(CSS,encoding='utf-8')
    page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>僵尸痒痒鼠 v9.49 用户使用手册</title><style>body{margin:0;padding:32px 24px;background:#f6f2ea;font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif}main{max-width:1000px;margin:auto;background:#fffaf2;padding:28px 36px;border:1px solid #e6dbca;border-radius:10px}@media print{body,main{padding:0;background:white;border:0}}'+CSS+'</style></head><body><main class="manual-content">'+content+'</main></body></html>'
    (ROOT/'用户使用手册.html').write_text(page,encoding='utf-8')
    assert content.count('<h2 ')==len(re.findall(r'^## ', source, re.M))
    assert '<script' not in content
    print('Manual rendered: shared in-app and offline content.')

if __name__=='__main__':main()
