"""Officially sourced server equivalence; unknown servers remain independent."""
import json
import sys
from pathlib import Path
from functools import lru_cache
ROOT=Path(__file__).resolve().parent
@lru_cache(maxsize=1)
def catalog():
 path=ROOT/'server-merges.json'
 if not path.exists():return {}
 value=json.loads(path.read_text('utf-8'));parent={}
 def find(x):
  parent.setdefault(x,x)
  if parent[x]!=x:parent[x]=find(parent[x])
  return parent[x]
 for group in value['groups']:
  ids=[str(x) for x in group['server_ids']]
  if len(ids)<2 or not group.get('sources'):raise ValueError('合区资料缺少官方依据')
  for id in ids[1:]:parent[find(id)]=find(ids[0])
 groups={}
 for id in list(parent):groups.setdefault(find(id),[]).append(id)
 return {id:min(members,key=lambda x:int(x)) for members in groups.values() for id in members}
def canonical(server):return catalog().get(str(server),str(server))
def same_server(a,b):return canonical(a)==canonical(b)
def matches(scope,roles):
 server,role=scope.split(':',1)
 return [r for r in roles if str(r.get('short_id'))==role and same_server(r.get('server_id'),server)]
