"""Explicit Gitee release upload. Dry-run by default; credentials come from the environment."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import uuid

REPO='xirry/JiangshiYys'
API='https://gitee.com/api/v5/repos/'+REPO


def request(path, token, payload=None, method=None, content_type='application/json'):
    data=payload if isinstance(payload,bytes) else json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(API+path,data=data,method=method,
        headers={'Authorization':'Bearer '+token,'Content-Type':content_type,'User-Agent':'JiangshiYys-Publisher'})
    try:
        with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise RuntimeError('Gitee operation failed (HTTP '+str(error.code)+')') from None


def save_feed(token, rows, existing):
    payload={'content':base64.b64encode(json.dumps(rows,ensure_ascii=False,indent=2).encode()).decode(),
             'message':'Update release feed','branch':'main'}
    if existing:payload['sha']=existing['sha']
    result=request('/contents/updates.json',token,payload,method='PUT' if existing else 'POST')
    if result is None:raise RuntimeError('Could not write the update feed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--notes',type=Path,required=True)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args()
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from app_updates import version,select_release
    version(args.tag)
    name=args.package.name;size=args.package.stat().st_size
    if not 0<size<100*1024*1024:raise ValueError('Gitee release attachment must be smaller than 100 MiB')
    digest='sha256:'+hashlib.sha256(args.package.read_bytes()).hexdigest()
    notes=args.notes.read_text('utf-8')
    # Validate the exact release filename and metadata before any remote mutation.
    asset={'name':name,'size':size,'digest':digest,'browser_download_url':'https://gitee.com/'+REPO+'/releases/download/'+args.tag+'/'+name}
    row={'tag_name':args.tag,'prerelease':args.tag.endswith('-experimental'),'draft':False,'body':notes,'assets':[asset]}
    if not select_release([row],'0.0',True,'gitee'):raise ValueError('Invalid package name or release metadata')
    print(json.dumps({'repository':REPO,'tag':args.tag,'file':name,'size':size,'sha256':digest[7:],'publish':args.publish},ensure_ascii=False,indent=2))
    if not args.publish:return
    token=os.environ.get('GITEE_TOKEN','')
    if not token:raise ValueError('Set GITEE_TOKEN in the environment before publishing')
    existing=request('/contents/updates.json?ref=main',token)
    feed=json.loads(base64.b64decode(existing['content']).decode()) if existing else []
    if not isinstance(feed,list):raise ValueError('Existing update feed is invalid')
    if not existing:save_feed(token,[],None)
    release=request('/releases/tags/'+args.tag,token)
    if release:raise ValueError('Release already exists; inspect its attachments before retrying')
    release=request('/releases',token,{'tag_name':args.tag,'name':args.tag,'body':notes,'target_commitish':'main','prerelease':row['prerelease']})
    if not release or not release.get('id'):raise RuntimeError('Could not create release')
    boundary='JiangshiYys'+uuid.uuid4().hex
    data=(('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="'+name+'"\r\nContent-Type: application/zip\r\n\r\n').encode()+args.package.read_bytes()+('\r\n--'+boundary+'--\r\n').encode())
    uploaded=request('/releases/'+str(release['id'])+'/attach_files',token,data,content_type='multipart/form-data; boundary='+boundary)
    if not uploaded or not uploaded.get('browser_download_url'):raise RuntimeError('Attachment upload did not return a download URL')
    asset['browser_download_url']=uploaded['browser_download_url']
    if not select_release([row],'0.0',True,'gitee'):raise RuntimeError('Returned attachment URL needs review; update feed was not changed')
    existing=request('/contents/updates.json?ref=main',token)
    if not existing:raise RuntimeError('Update feed disappeared; inspect repository before retrying')
    feed=json.loads(base64.b64decode(existing['content']).decode())
    save_feed(token,[row,*[item for item in feed if item.get('tag_name')!=args.tag]],existing)
    print('Gitee release and checksum feed published.')


if __name__=='__main__':main()
