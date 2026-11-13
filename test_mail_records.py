from pathlib import Path
import json,time,copy,datetime as dt
from blue_tickets import BlueStore
root=Path(__file__).resolve().parent/'test-results'/('mail-ledger-'+str(time.time_ns()));store=BlueStore(root)
roles=[{'id':'a','nickname':'演示角色','server':'测试区','short_id':'111','server_id':'222'}]
s=store.load(roles);s=store.subjects(['a'],s['revision'],roles)
stamp=int(dt.datetime(2026,11,11,20,0,tzinfo=dt.timezone(dt.timedelta(hours=8))).timestamp())
def mail(uid,n,offset=0,kind=400179):return {'uid':uid,'type':kind,'reason':'gym2_attack' if kind==400179 else 'gym_break_fail_reward','time':stamp+offset,'items':[[900001,100],[490001,n],[200001,8],[987654,7]] if n else [[900001,100],[200001,8]]}
def env(rows):return {'role':{'nickname':'演示角色','short_id':111,'server_id':222},'dojo_mails':rows,'loaded_count':20}
r=store.import_mail(env([mail('one',0),mail('base',0,30,400175)]),s['revision'],roles);assert r['added']==1
row=r['snapshot']['records'][0];assert row['first']==0 and row['second'] is None
r=store.import_mail(env([mail('one',0),mail('two',6,3600),mail('base',0,30,400175)]),r['snapshot']['revision'],roles)
assert r['added']==1 and r['duplicates']==1 and r['snapshot']['records'][0]['second']==6
receipts=store.mail_records(roles);assert len(receipts)==2 and receipts[0]['items'][-1]==[987654,7]
rev=r['snapshot']['revision'];history=len(store.history('a','2026-11-11'))
r=store.import_mail(env([mail('two',6,3600),mail('one',0)]),rev,roles)
assert not r['added'] and r['snapshot']['revision']==rev and len(store.history('a','2026-11-11'))==history
# Manual corrections remain authoritative while complete resource receipts are kept.
manual={**r['snapshot']['records'][0],'first':9};s=store.save([manual],rev,False,roles)
r=store.import_mail(env([mail('one',0),mail('two',6,3600)]),s['revision'],roles)
assert r['snapshot']['records'][0]['first']==9 and r['warnings']
# Invalid payload cannot partially append receipts; stale revisions also fail atomically.
for envelope,revision in [(env([mail('new',2),{**mail('broken',1),'items':[[1,-3]]}]),r['snapshot']['revision']), (env([mail('stale',2)]),-1), ({**env([]),'role':{'short_id':999,'server_id':222}},r['snapshot']['revision'])]:
 before=store.mail_records(roles)
 try:store.import_mail(envelope,revision,roles)
 except ValueError:pass
 else:raise AssertionError('invalid or stale import accepted')
 assert store.mail_records(roles)==before
# Empty loaded set never implies zero rewards, nor removes stored receipts.
r=store.import_mail(env([]),r['snapshot']['revision'],roles);assert len(store.mail_records(roles))==2
r=store.import_mail(env([mail('three',1,7200)]),r['snapshot']['revision'],roles);assert r['warnings'] and r['snapshot']['records'][0]['first']==9
print('PASS: all resource IDs and quantities, base rewards, zero tickets, partial completion, unique-mail replay deduplication, manual protection, multi-mail warning, wrong-role/stale/invalid atomic rejection, empty-cache preservation.')

# Realm cards keep game-provided stars; the resource page leaves old blue data alone.
resource_store=BlueStore(root/'resources-only');snap=resource_store.load(roles);snap=resource_store.subjects(['a'],snap['revision'],roles)
e=env([{**mail('cards',1),'items':[[200001,79],[200002,49],[490001,1]]}]);e['item_names']={'200001':'太阴符咒','200002':'太阴符咒'};e['item_meta']={'200001':{'name':'太阴符咒','kind':'realm_card','stars':1},'200002':{'name':'太阴符咒','kind':'realm_card','stars':2}}
r=resource_store.import_mail(e,snap['revision'],roles,project_blue=False)
assert not r['snapshot']['records'] and r['added']==1
saved=resource_store.mail_records(roles)[0];assert saved['item_meta']['200001']['stars']==1 and saved['item_meta']['200002']['stars']==2
r=resource_store.import_mail(e,r['snapshot']['revision'],roles,project_blue=False);assert r['added']==0 and len(resource_store.mail_records(roles))==1
bad=copy.deepcopy(e);bad['item_meta']['200001']['stars']=7
try:resource_store.import_mail(bad,r['snapshot']['revision'],roles,project_blue=False)
except ValueError:pass
else:raise AssertionError('invalid star accepted')
assert resource_store.mail_records(roles)[0]['item_meta']['200001']['stars']==1
print('PASS: 1/2-star same-name cards stored separately, invalid stars rejected, no legacy blue projection, replay deduplication intact.')

# Old basic receipts remain on disk but are excluded from the public ledger.
with store._connect() as db:
    db.execute('INSERT INTO mail_rewards VALUES(?,?,?,?)',('old-scope','old-base','a',json.dumps({'uid':'old-base','type':400175,'date':'2026-11-11','items':[[900016,10]],'time':stamp})))
assert all(r['type']!=400175 for r in store.mail_records(roles))
with store._connect() as db:assert db.execute("SELECT COUNT(*) FROM mail_rewards WHERE uid='old-base'").fetchone()[0]==1
print('PASS: basic-reward imports skipped, historical basic receipts hidden without deletion.')

# Empty reads and reward-less mails never create standalone role/day records.
empty_store=BlueStore(root/'empty-standalone');snapshot=empty_store.mail_archives([])
for rows in ([],[mail('basic-only',0,kind=400175)],[{**mail('empty',0),'items':[]}],[{**mail('zero-only',0),'items':[[490001,0]]}]):
    result=empty_store.import_mail(env(rows),snapshot['revision'],[],project_blue=False,standalone=True)
    assert result['added']==0 and not result['snapshot']['roles']
    assert result['snapshot']['revision']==snapshot['revision']
    with empty_store._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM mail_archives').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM mail_rewards').fetchone()[0]==0
real=empty_store.import_mail(env([mail('real',0)]),snapshot['revision'],[],project_blue=False,standalone=True)
assert real['added']==1 and len(real['snapshot']['roles'])==1
again=empty_store.import_mail(env([]),real['snapshot']['revision'],[],project_blue=False,standalone=True)
assert again['snapshot']==real['snapshot'] and len(empty_store.mail_records([]))==1
# Old empty entries are hidden, with all on-disk data retained.
with empty_store._connect() as db:
    db.execute('INSERT INTO mail_archives VALUES(?,?,?,?)',('empty-scope','empty-archive','Old empty','Test'))
    db.execute('INSERT INTO mail_rewards VALUES(?,?,?,?)',('empty-scope','empty-old','empty-archive',json.dumps({'uid':'empty-old','type':400179,'items':[],'date':'2026-11-11'})))
assert len(empty_store.mail_archives([])['roles'])==1 and len(empty_store.mail_records([]))==1
with empty_store._connect() as db:
    assert db.execute("SELECT COUNT(*) FROM mail_archives WHERE scope='empty-scope'").fetchone()[0]==1
    assert db.execute("SELECT COUNT(*) FROM mail_rewards WHERE scope='empty-scope'").fetchone()[0]==1
print('PASS: empty/basic-only/zero-only reads create no archive or receipt; existing rewards survive empty reads; legacy empty entries hidden without deletion.')
