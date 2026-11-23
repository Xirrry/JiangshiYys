from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from io import BytesIO
import copy,json,time
from blue_tickets import BlueStore

class Output(BytesIO):
    def close(self):pass
stamp=int(time.time())-60
souls=[[110006,1,{'qua':6,'suitid':300015,'uuid':'private-'+str(i),'rattr':[['speed',2]]}] for i in range(240)]
raw={'uid':'long-boss','type':622502,'reason':'gc_receive_settle_reward_boss','time':stamp,'items':souls+[[900001,90000],[490001,2]]}
position={'uid':'position','type':622503,'reason':'gc_receive_settle_reward_position','time':stamp,'items':[[900001,40000],[200004,2]]}
unrelated={**raw,'uid':'unrelated','type':622504}
basic={**raw,'uid':'basic','type':400175,'reason':'gym_break_fail_reward'}
tables={'DATA_CURRENCY':SimpleNamespace(data={900001:{'name':'金币'},490001:{'name':'神秘的符咒'}}),'DATA_JJCARD':SimpleNamespace(data={200004:{'name':'太阴符咒','star':4}})}
modules={'com.MailData':SimpleNamespace(mailDataList=[basic]*120+[unrelated,raw,position]),'Globals':SimpleNamespace(player1=SimpleNamespace(name='测试角色',server_id=123,short_id=456)),'DynamicConfigData':SimpleNamespace(**tables)}
out=Output()
with patch.dict('sys.modules',modules):exec(Path('hardware/mail-reader/mail_script.py').read_text(encoding='utf-8'),{'f':out})
envelope=json.loads(out.getvalue())
assert 'error' not in envelope,envelope
assert len(envelope['dojo_mails'])==2 and envelope['loaded_count']==123
boss=envelope['dojo_mails'][0]
assert len(boss['items'])==3 and [-1006,240] in boss['items']
assert boss['reward_quantity']==90242 and boss['attachments_complete']
assert envelope['item_names']['-1006']=='6星御魂' and envelope['item_meta']['200004']['stars']==4
assert 'private-' not in out.getvalue().decode() and 'rattr' not in out.getvalue().decode()
root=Path('test-results')/('xiajian-mail-'+str(time.time_ns()));store=BlueStore(root)
result=store.import_mail(envelope,store.mail_archives([])['revision'],[],standalone=True,project_blue=False)
assert result['added']==2
repeat=store.import_mail(envelope,result['snapshot']['revision'],[],standalone=True,project_blue=False)
assert repeat['added']==0 and repeat['duplicates']==2 and repeat['snapshot']['revision']==result['snapshot']['revision']
partial=copy.deepcopy(envelope);partial['dojo_mails'][0]['items']=[[490001,1]];partial['dojo_mails'][0]['reward_quantity']=1
again=store.import_mail(partial,repeat['snapshot']['revision'],[],standalone=True,project_blue=False)
assert again['added']==0 and again['warnings'] and [-1006,240] in next(m for m in store.mail_records([]) if m['uid']=='long-boss')['items']
before=store.mail_records([])
for change in ({'attachments_complete':False},{'reward_quantity':1}):
    invalid=copy.deepcopy(envelope);invalid['dojo_mails'][0].update(change)
    try:store.import_mail(invalid,again['snapshot']['revision'],[],standalone=True,project_blue=False)
    except ValueError:pass
    else:raise AssertionError('incomplete attachment accepted')
    assert store.mail_records([])==before
# Backend also aggregates raw soul data, so alternate readers cannot store private details.
raw_env={**envelope,'dojo_mails':[{**raw,'uid':'raw-stars'}]}
saved=store.import_mail(raw_env,again['snapshot']['revision'],[],standalone=True,project_blue=False)
entry=next(m for m in store.mail_records([]) if m['uid']=='raw-stars')
assert [-1006,240] in entry['items'] and 'private-' not in json.dumps(entry)
bad=copy.deepcopy(raw_env);bad['dojo_mails'][0]['items'][0][2]['qua']=0
try:store.import_mail(bad,saved['snapshot']['revision'],[],standalone=True,project_blue=False)
except ValueError:pass
else:raise AssertionError('unknown soul stars accepted')
print('PASS: full mailbox beyond 100 mails, 242 attachments, soul quantity-only aggregation, true card stars, exact reward sources, replay deduplication, partial-claim preservation and atomic incomplete-payload rejection.')
