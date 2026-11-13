from pathlib import Path
from unittest.mock import patch
import time
import desktop_api,role_reader
from blue_tickets import BlueStore
root=Path(__file__).resolve().parent/'test-results'/('mail-identity-'+str(time.time_ns()));api=desktop_api.DesktopApi(root)
roles=[{'id':'bound','confirmed':True,'nickname':'角色','short_id':'123','server_id':'10003'}]
e={'role':{'nickname':'角色','short_id':123,'server_id':10001},'dojo_mails':[]}
with patch.object(api,'_roles',return_value=roles),patch.object(api,'_state',return_value={'pid':100,'stamp':200}),patch.object(role_reader,'read_identity',return_value={'nickname':'角色','short_id':'123','server_id':'10003'}):
 assert api._mail_bound_role(e,100,200)=='bound'
 for pid,stamp in [(101,200),(100,201)]:
  try:api._mail_bound_role(e,pid,stamp)
  except ValueError:pass
  else:raise AssertionError('untracked window accepted')
 with patch.object(role_reader,'read_identity',return_value={'nickname':'其他角色','short_id':'123','server_id':'10003'}):
  try:api._mail_bound_role(e,100,200)
  except ValueError:pass
  else:raise AssertionError('wrong login identity accepted')
 with patch.object(role_reader,'read_identity',side_effect=ValueError('stale login')):
  try:api._mail_bound_role(e,100,200)
  except ValueError:pass
  else:raise AssertionError('stale login accepted')
 store=BlueStore(root);s=store.load(roles);s=store.subjects(['bound'],s['revision'],roles)
 r=store.import_mail(e,s['revision'],roles,project_blue=False,resolved_role_id='bound');assert r['added']==0
print('PASS: merged-server login alias verified through owned PID/stamp/fresh login config; unrelated windows, changed stamps, wrong names and stale login rejected.')
