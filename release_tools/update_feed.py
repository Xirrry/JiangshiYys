"""After publishing a Release, refresh and commit the public update feed."""
import json
from pathlib import Path
import shutil
import subprocess
ROOT = Path(__file__).resolve().parents[1]
cli = shutil.which('gh') or str(ROOT / 'release_tools/github-cli/gh.exe')
completed = subprocess.run([cli, 'api', 'repos/Xirrry/JiangshiYys/releases?per_page=30'], check=True, capture_output=True, text=True, encoding='utf-8')
rows = json.loads(completed.stdout)
feed = [{'tag_name': r['tag_name'], 'prerelease': r['prerelease'], 'draft': False, 'body': r.get('body', ''),
         'assets': [{k: a.get(k) for k in ('name', 'size', 'digest', 'browser_download_url')} for a in r['assets']]}
        for r in rows if not r['draft']]
(ROOT / 'updates.json').write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding='utf-8')
print('Public update feed refreshed:', len(feed), 'releases. Commit updates.json after review.')
