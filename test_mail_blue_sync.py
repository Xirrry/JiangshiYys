from pathlib import Path
import datetime as dt,time,copy
from blue_tickets import BlueStore
root=Path(__file__).resolve().parent/'test-results'/('mail-blue-sync-'+str(time.time_ns()))
s=BlueStore(root)
stamp=int(dt.datetime(2026,11,11,12,0,tzinfo=dt.timezone(dt.timedelta(hours=8))).timestamp())
def mail(uid,n,offset=0):return {'uid':uid,'type':400179,'reason':'gym2_attack','time':stamp+offset,'items':[[900001,100],[490001,n]]}
def env(rows,role=111):return {'role':{'nickname':'同步角色','server':'Test','short_id':role,'server_id':222},'dojo_mails':rows,'loaded_count':len(rows)}
def read(rows,roles=(),who=111,project=False):return s.import_mail(env(rows,who),s.mail_archives(roles)['revision'],roles,project_blue=project,standalone=True)
# Already saved receipts sync without any running game or launcher account.
read([mail('one',0)])
r=s.sync_mail_blue(s.load([])['revision'],[]);assert r['synced']==1
snap=r['snapshot'];key=snap['roles'][0]['id'];record=snap['records'][0]
assert snap['roles'][0]['selected'] and snap['roles'][0]['active'] and record['first']==0 and record['second'] is None
assert not s.sync_mail_blue(snap['revision'],[])['synced']
# A second mail updates the automatically generated partial record.
read([mail('one',0),mail('two',6,3600)],project=True)
snap=s.load([]);assert len(snap['records'])==1 and snap['records'][0]['second']==6
rev=snap['revision'];assert not s.sync_mail_blue(rev,[])['synced'] and s.load([])['revision']==rev
# Independent roles remain editable/selectable; manual edits are not overwritten.
manual={**snap['records'][0],'first':9};snap=s.save([manual],rev,False,[])
r=s.sync_mail_blue(snap['revision'],[]);assert r['warnings'] and r['snapshot']['records'][0]['first']==9
s.subjects([],r['snapshot']['revision'],[]);snap=s.load([]);assert not snap['roles'][0]['selected']
s.subjects([key],snap['revision'],[])
# Exact launcher identity reuses its ID instead of duplicating its role.
roles=[{'id':'bound','nickname':'Bound','server':'Test','short_id':333,'server_id':222}]
read([mail('bound-one',3)],roles,333)
r=s.sync_mail_blue(s.load(roles)['revision'],roles)
assert any(x['role_id']=='bound' and x['first']==3 for x in r['snapshot']['records'])
assert len([x for x in r['snapshot']['roles'] if x['id']=='bound'])==1
# Excess mail and non-round/empty receipts never fabricate a daily record.
read([mail('ex1',1),mail('ex2',2,1),mail('ex3',3,2)],who=444)
r=s.sync_mail_blue(s.load([])['revision'],[])
assert r['warnings'] and not any(x['role_id']==s._archive_id('222:444') for x in r['snapshot']['records'])
# Manual deletion stays deleted (derived marker prevents re-creation).
snap=s.load([]);current=next(x for x in snap['records'] if x['role_id']==key)
s.save([{**current,'remove':True}],snap['revision'],False,[])
r=s.sync_mail_blue(s.load([])['revision'],[]);assert not any(x['role_id']==key for x in r['snapshot']['records'])
try:s.sync_mail_blue(-1,[])
except ValueError:pass
else:raise AssertionError('stale sync accepted')
print('PASS: saved receipts, standalone roles, zero blue, second round, repeated sync, manual edits/deletions, bound identity, excess mails, stale revision.')

# The public blue-page load backfills historical receipts; manual sync is idempotent.
import desktop_api
from unittest.mock import patch
api=desktop_api.DesktopApi(root/'api')
with patch.object(api,'_roles',return_value=[]):
    rev=api._blue.mail_archives([])['revision']
    api._blue.import_mail(env([mail('api-old',4)]),rev,[],project_blue=False,standalone=True)
    loaded=api.blue_records('load');assert loaded['ok'] and loaded['data']['records'][0]['first']==4
    synced=api.blue_records('sync_mail',{'revision':loaded['data']['revision']})
    assert synced['ok'] and synced['data']['synced']==0
    assert not api.blue_records('sync_mail',{'revision':-1})['ok']
print('PASS: blue-page API backfills saved mail automatically; explicit sync respects revision and replay guards.')
