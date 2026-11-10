import uuid,sys,subprocess
from single_instance import Instance
name='Local\\JiangshiYys-test-'+uuid.uuid4().hex
first=Instance(name);assert not first.duplicate
second=Instance(name);assert second.duplicate
code='from single_instance import Instance; i=Instance('+repr(name)+'); print(i.duplicate); i.close()'
result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True)
assert result.stdout.strip()=='True'
first.close();third=Instance(name);assert not third.duplicate;third.close()
print('PASS: single instance across processes, duplicate handle release, new acquisition after exit; fixture mutex only')
