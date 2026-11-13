from pathlib import Path
import time,datetime as dt,json
from blue_tickets import BlueStore
import server_merges
root=Path(__file__).resolve().parent/'test-results'/('mail-merge-'+str(time.time_ns()))
stamp=int(dt.datetime(2026,11,11,12,tzinfo=dt.timezone(dt.timedelta(hours=8))).timestamp())
roles=[{'id':'night','nickname':'演示角色','server':'夜之月','short_id':'12345678','server_id':'10003'}]
def env(server=10001,who=12345678,uid='mail',n=2):
 return {'role':{'nickname':'演示角色','server_id':server,'short_id':who,'server':'春之樱'},'dojo_mails':[{'uid':uid,'type':400179,'reason':'gym2_attack','time':stamp,'items':[[490001,n]]}]}
s=BlueStore(root)
# Simulate an archive already synchronized before merge support, and a selected empty original role.
r=s.import_mail(env(),s.mail_archives([])['revision'],[],project_blue=True,standalone=True)
source=r['snapshot']['roles'][0]['id'];before=s.load(roles);s.subjects([source,'night'],before['revision'],roles)
r=s.sync_mail_blue(s.load(roles)['revision'],roles);snap=r['snapshot']
assert len([x for x in snap['roles'] if x['selected']])==1
assert len(snap['records'])==1 and snap['records'][0]['role_id']=='night' and snap['records'][0]['first']==2
assert next(x for x in snap['roles'] if x['id']=='night')['server']=='夜之月'
with s._connect() as db:
 assert db.execute('SELECT COUNT(*) FROM records WHERE role_id=?',(source,)).fetchone()[0]==1
 assert db.execute('SELECT COUNT(*) FROM mail_rewards').fetchone()[0]==1
rev=snap['revision'];again=s.sync_mail_blue(rev,roles);assert again['snapshot']['revision']==rev
# Repeated reads and alternate entry scopes share the same mail UID, not double count.
r=s.import_mail(env(10003),rev,roles,project_blue=True,standalone=True)
assert len(s.load(roles)['records'])==1 and s.load(roles)['records'][0]['first']==2
# Same nickname and ID in an unrelated server are kept independent.
r=s.import_mail(env(10002),r['snapshot']['revision'],roles,project_blue=True,standalone=True)
assert len(s.load(roles)['records'])==2
assert server_merges.same_server(10001,10003) and not server_merges.same_server(10001,10002)
# Conflicting manual values never silently overwrite or hide one side.
t=BlueStore(root/'conflict');t.import_mail(env(),0,[],project_blue=True,standalone=True)
snap=t.load(roles);t.subjects([source,'night'],snap['revision'],roles)
snap=t.load(roles)
t.save([{**snap['records'][0],'first':5},{**snap['records'][0],'role_id':'night','first':9}],snap['revision'],False,roles)
r=t.sync_mail_blue(t.load(roles)['revision'],roles)
assert r['warnings'] and len(r['snapshot']['records'])==2
assert sorted(x['first'] for x in r['snapshot']['records'])==[5,9]
# New reads directly match merged login identities without a duplicate empty row.
u=BlueStore(root/'fresh');u.import_mail(env(),0,roles,project_blue=True,standalone=True)
assert u.load(roles)['records'][0]['role_id']=='night'
assert len([x for x in u.load(roles)['roles'] if x['selected']])==1
print('PASS: merged server match, old duplicate consolidation, original label, retained originals, repeated sync, cross-scope mail dedup, unrelated server isolation, manual conflict protection.')

# Removing a canonical record stays removed through future alias reconciliation.
v=BlueStore(root/'deleted');v.import_mail(env(),0,[],project_blue=True,standalone=True)
v.sync_mail_blue(v.load(roles)['revision'],roles);snap=v.load(roles)
v.save([{**snap['records'][0],'remove':True}],snap['revision'],False,roles)
v.sync_mail_blue(v.load(roles)['revision'],roles);assert not v.load(roles)['records']
# Once linked, losing the launcher entry cannot split the archive again.
w=BlueStore(root/'removed-binding');w.import_mail(env(),0,roles,project_blue=True,standalone=True)
w.sync_mail_blue(w.load([])['revision'],[]);snap=w.load([])
assert len(snap['records'])==1 and snap['records'][0]['role_id']=='night'
assert server_merges.same_server(15004,15033)
print('PASS: canonical manual deletion preserved, bindings may disappear without a split, official Bilibili group recognized.')

# Every bundled server is handled; only official, ID-resolved groups are equated.
from urllib.parse import urlparse
catalog=json.loads((Path(__file__).resolve().parent/'server-merges.json').read_text('utf-8'))
servers=json.loads((Path(__file__).resolve().parent/'servers.json').read_text('utf-8'))['servers']
known={str(x['id']) for x in servers}
for group in catalog['groups']:
 assert set(group['server_ids'])<=known
 assert all(urlparse(source['url']).hostname=='yys.163.com' for source in group['sources'])
 assert all(server_merges.same_server(group['server_ids'][0],x) for x in group['server_ids'])
for server in known-set(server_merges.catalog()):assert server_merges.canonical(server)==server
print('PASS: all bundled server IDs covered, official URLs verified, unknown groups remain independent.')
