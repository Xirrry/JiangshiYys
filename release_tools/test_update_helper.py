"""Native switch/rollback tests only in a retained synthetic fixture, no user app/data."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json,os,shutil,subprocess,sys,time,uuid
ROOT=Path(__file__).resolve().parents[1]
report=json.loads((ROOT/'release_tools/latest-binary-release.json').read_text(encoding='utf-8'))
base=ROOT/'test-results'/('native-update-'+uuid.uuid4().hex);base.mkdir(parents=True)
shutil.copy2(ROOT/'release_tools/updater_fixture.c',base/'stub.c')
# Explicit native command, no shell delete/move operations.
command='@echo off\ncall "D:\\App\\Microsoft Visual Studio\\18\\Community\\VC\\Auxiliary\\Build\\vcvarsall.bat" x64 >nul\ncd /d "%~dp0"\ncl /nologo /utf-8 /O2 /MT stub.c /Festub.exe /link /SUBSYSTEM:WINDOWS\nexit /b %errorlevel%\n'
(base/'build.cmd').write_text(command,encoding='utf-8',newline='\r\n')
p=subprocess.run(['cmd','/c',str(base/'build.cmd')],capture_output=True);assert p.returncode==0,p.stdout.decode(errors='replace')
api=ctypes.WinDLL('kernel32',use_last_error=True);api.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
def stamp(process):
 times=[wintypes.FILETIME() for _ in range(4)];assert api.GetProcessTimes(int(process._handle),*[ctypes.byref(x) for x in times]);return times[0].dwLowDateTime+(times[0].dwHighDateTime<<32)
def fixture(label,fail=False):
 parent=base/label;parent.mkdir();root=parent/'软件目录';root.mkdir();(root/'data').mkdir();(root/'brand.json').write_text('old',encoding='utf-8');(root/'data'/'keep.txt').write_text('fixture-private',encoding='utf-8');shutil.copy2(base/'stub.exe',root/'僵尸痒痒鼠.exe')
 job=parent/('.JiangshiYys-update-'+uuid.uuid4().hex);fresh=job/'new';fresh.mkdir(parents=True);(fresh/'brand.json').write_text('new',encoding='utf-8');shutil.copy2(base/'stub.exe',fresh/'僵尸痒痒鼠.exe');shutil.copy2(Path(report['package'])/'ApplyUpdate.exe',job/'ApplyUpdate.exe')
 if fail:(fresh/'fail-start.txt').write_text('fixture',encoding='utf-8')
 # Verify resolved directory targets are inside this exact fixture before any helper move.
 for target in [root,job,fresh,job/'backup',job/'failed']:
  assert target.resolve().is_relative_to(base.resolve()) and target.resolve()!=base.resolve()
 dummy=subprocess.Popen([sys.executable,'-c','import time; time.sleep(1)'])
 helper=subprocess.Popen([str(job/'ApplyUpdate.exe'),str(root),str(dummy.pid),str(stamp(dummy))],cwd=job)
 dummy.wait(timeout=5)
 return root,job,helper
root,job,helper=fixture('success')
assert helper.wait(timeout=15)==0
assert (root/'brand.json').read_text()=='new'
assert (root/'data'/'keep.txt').read_text()=='fixture-private'
assert (job/'backup'/'brand.json').read_text()=='old'
assert not (job/'backup'/'data').exists()
assert 'Update complete' in (job/'update-result.txt').read_text()
root,job,helper=fixture('rollback',True)
deadline=time.monotonic()+15
while time.monotonic()<deadline:
 if (job/'update-result.txt').exists():break
 time.sleep(.1)
assert (root/'brand.json').read_text()=='old'
assert (root/'data'/'keep.txt').read_text()=='fixture-private'
assert (job/'failed'/'brand.json').read_text()=='new'
assert 'restored' in (job/'update-result.txt').read_text()
# Dismiss only the helper process created in this synthetic test, which presents a rollback warning.
if helper.poll() is None:helper.terminate();helper.wait(timeout=5)
invalid=base/'mismatched-root';invalid.mkdir()
p=subprocess.run([str(job/'ApplyUpdate.exe'),str(invalid),'1','1'],cwd=job,timeout=5)
assert p.returncode==2 and invalid.is_dir()
print('PASS: native successful switch, original data retained without duplicate, previous code backed up, failed launch rollback and out-of-scope path rejection. All fixtures retained: '+str(base))
