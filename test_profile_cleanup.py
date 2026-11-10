"""Validate deletion targets/order with mocked OS removals: no bulk deletion in tests."""
from pathlib import Path
from unittest.mock import patch
import _winapi
import os
import time
import profile_cleanup as cleanup

fixture=Path(__file__).resolve().parent/'test-results'/f'cleanup-{time.time_ns()}'
base=fixture/'profiles';root=base/'private-role';shared=fixture/'shared-game'
(root/'Documents').mkdir(parents=True);shared.mkdir()
(root/'Documents/login-cache').write_bytes(b'private')
(root/'private-config').write_bytes(b'config')
(shared/'resource.bin').write_bytes(b'shared-game-resource'*1000)
_winapi.CreateJunction(str(shared),str(root/'res'))
os.link(shared/'resource.bin',root/'linked-resource.bin')
plan=cleanup.inspect(base,root)
assert plan['bytes']==len(b'privateconfig')
assert plan['resource_links']==1 and plan['hardlinked_files']==1 and plan['files']==3
assert all(not (Path(row['path']).parts and Path(row['path']).parts[0]=='res' and len(Path(row['path']).parts)>1) for row in plan['entries'])
calls=[]
with patch.object(cleanup.os,'unlink',side_effect=lambda p:calls.append(('file',Path(p)))),patch.object(cleanup.os,'rmdir',side_effect=lambda p:calls.append(('dir',Path(p)))):
    result=cleanup.execute(base,plan)
assert result['bytes']==13
assert calls[-1]==('dir',root)
assert ('dir',root/'res') in calls
assert ('file',root/'Documents/login-cache') in calls
assert all(path==root or path.is_relative_to(root) for _,path in calls)
assert (shared/'resource.bin').read_bytes()==b'shared-game-resource'*1000
assert (root/'Documents/login-cache').exists()  # removal calls were intentionally mocked
# A content change since preview invalidates the entire plan before any removal.
(root/'private-config').write_bytes(b'updated-config')
with patch.object(cleanup.os,'unlink') as unlink,patch.object(cleanup.os,'rmdir') as rmdir:
    try:cleanup.execute(base,plan);raise AssertionError('stale plan accepted')
    except ValueError:pass
    unlink.assert_not_called();rmdir.assert_not_called()
for invalid in (base,shared,base/'outside/../../escape'):
    try:cleanup.inspect(base,invalid);raise AssertionError('unsafe root accepted')
    except ValueError:pass
_winapi.CreateJunction(str(shared),str(base/'redirected-role'))
try:cleanup.inspect(base,base/'redirected-role');raise AssertionError('redirected root accepted')
except ValueError:pass
assert cleanup.inspect(base,base/'missing-role')['entries']==[]
print('PASS: private-byte accounting, no traversal into shared junctions, hardlink accounting, child-first explicit targets, changed-cache refusal, root/escape/junction guards. All OS removal calls mocked; no files deleted.')

# One explicit fixture file is actually unlinked; directory removals remain mocked.
single=fixture/'single/profiles/role';single.mkdir(parents=True)
marker=single/'single-delete-marker.txt';marker.write_bytes(b'test-only')
assert marker.resolve().is_relative_to(fixture.resolve())
with patch.object(cleanup.os,'rmdir'):
    cleanup.execute(single.parent,cleanup.inspect(single.parent,single))
assert not marker.exists()
assert (shared/'resource.bin').exists()
print('PASS: one explicit test marker file actually removed; no real directory or user file deleted.')
