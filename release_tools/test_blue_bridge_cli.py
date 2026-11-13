import json,sys
sys.stdin.reconfigure(encoding="utf-8")
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from desktop_api import DesktopApi
root=Path(sys.argv[1]).resolve()
assert root.is_relative_to((ROOT/'test-results').resolve()) and root.name.startswith('blue-ui-')
api=DesktopApi(root)
result=api.blue_records(sys.argv[2],json.loads(sys.stdin.read() if sys.argv[3]=='--stdin' else sys.argv[3]))
print(json.dumps(result,ensure_ascii=True))
