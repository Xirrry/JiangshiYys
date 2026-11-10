"""Create a build-only package and compile all first-party Python to one native PYD.
Development sources and user data are never changed or deleted.
"""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
FILES=['app.pyw','desktop_api.py','launcher.pyw','cache_import.py','close_guard.py','game_preferences.py',
       'game_discovery.py','device_identity.py','profile_cleanup.py','laoyu_controller.py','laoyu_support.py','launcher_workspace.py',
       'pinganzhi_sync.py','proxy_dns.py','proxy_support.py','role_reader.py','window_layout.py',
       'proxy-engine-experiment/game_tcp_trial.py','proxy-engine-experiment/trial_job.py','proxy-engine-experiment/dns_bridge.py']
OWN={Path(name).stem for name in FILES}-{'launcher'}|{'business','module_properties'}
COMMAND="import yys_core; yys_core.main()"

class Imports(ast.NodeTransformer):
    def visit_Import(self,node):
        result=[]
        for alias in node.names:
            if alias.name in OWN:result.append(ast.ImportFrom(module=None,names=[alias],level=1))
            else:result.append(ast.Import(names=[alias]))
        return result
    def visit_ImportFrom(self,node):
        if node.module in OWN and node.level==0:node.level=1
        return node
    def visit_Assign(self,node):
        if '__file__' in ast.unparse(node.value):
            ids=[t.id for t in node.targets if isinstance(t,ast.Name)]
            if 'HERE' in ids:node.value=ast.parse("Path(sys.executable).resolve().parent.parent / 'proxy-engine-experiment'",mode='eval').body
            elif 'ROOT' in ids:node.value=ast.parse('Path(sys.executable).resolve().parent.parent',mode='eval').body
        return self.generic_visit(node)
    def visit_Call(self,node):
        node=self.generic_visit(node)
        if isinstance(node.func,ast.Name) and node.func.id=='__import__' and node.args and isinstance(node.args[0],ast.Constant) and node.args[0].value in OWN:
            node.args[0]=ast.Constant('yys_core.'+node.args[0].value)
            node.keywords.append(ast.keyword(arg='fromlist',value=ast.List(elts=[ast.Constant('*')],ctx=ast.Load())))
        return node

PROPERTIES='''"""Original minimal lazy-value adapter for the pywebview module-property API."""
class module_property:
    def __init__(self,f): self._resolve=f
    def _get_current_object(self): return self._resolve()
    def __getattr__(self,key): return getattr(self._resolve(),key)
    def __iter__(self): return iter(self._resolve())
    def __len__(self): return len(self._resolve())
    def __getitem__(self,key): return self._resolve()[key]
    def __contains__(self,key): return key in self._resolve()
    def __bool__(self): return bool(self._resolve())
    def __repr__(self): return repr(self._resolve())
    def __str__(self): return str(self._resolve())
    def __int__(self): return int(self._resolve())
    def __index__(self): return self._resolve().__index__()
    def __eq__(self,other): return self._resolve()==other
    def __ne__(self,other): return self._resolve()!=other
    def __hash__(self): return hash(self._resolve())
'''

ENTRY='''"""Compiled application and controller entry dispatcher."""
import sys
def main():
    args=sys.argv[1:]
    if args and args[0]=='--tcp':
        sys.argv=[sys.argv[0],*args[1:]]
        from .game_tcp_trial import main as run
        return run()
    if args and args[0]=='--laoyu':
        import argparse,json
        from .laoyu_controller import run
        p=argparse.ArgumentParser();p.add_argument('--role',required=True);p.add_argument('--proxy',required=True);p.add_argument('--ticket',required=True);p.add_argument('--port',type=int,default=22999);p.add_argument('--game-prefs')
        a=p.parse_args(args[1:])
        return run(a.role,a.proxy,a.ticket,a.port,json.loads(a.game_prefs) if a.game_prefs else None)
    from pathlib import Path
    root=Path(sys.executable).resolve().parent.parent
    try:
        from .app import main as run
        return run()
    except Exception:
        import traceback,ctypes
        (root/'desktop-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        ctypes.windll.user32.MessageBoxW(None,'界面未能打开，详情见 desktop-error.log。','启动失败',0)
        raise
'''

def main():
    stage=ROOT/'release_tools'/('compiled-'+time.strftime('%Y%m%d-%H%M%S'))
    package=stage/'yys_core';package.mkdir(parents=True,exist_ok=False)
    for file in FILES:
        src=(ROOT/file).read_text(encoding='utf-8');name=Path(file).stem
        if name=='launcher':name='business'
        if name=='desktop_api':
            start=src.index("        loader = importlib.machinery.SourceFileLoader(")
            end=src.index('        self._root =',start)
            src=src[:start]+'        from . import business\n        self._app = business\n'+src[end:]
            src=src.replace("[sys.executable,str(ROOT/'laoyu_controller.py'),",f"[sys.executable,'-c',{COMMAND!r},'--laoyu',")
            src=src.replace("[sys.executable, str(engine / 'game_tcp_trial.py'),",f"[sys.executable,'-c',{COMMAND!r},'--tcp',")
            src=src.replace("'game_tcp_trial.py'","'../yys_core.pyd'").replace("ROOT/'laoyu_controller.py'","ROOT/'yys_core.pyd'")
        if name=='laoyu_controller':
            start=src.index('        loader=importlib.machinery.SourceFileLoader(')
            end=src.index('        cfg=app.read_json(',start)
            src=src[:start]+'        from . import business as app\n'+src[end:]
        if name=='game_tcp_trial':
            start=src.index("    loader = importlib.machinery.SourceFileLoader(")
            end=src.index('    cfg = app.read_json(',start)
            src=src[:start]+'    from . import business as app\n'+src[end:]
            old="[str(Path(__file__).resolve()), '--broker', str(session)]"
            assert old in src
            src=src.replace(old,f"['-c',{COMMAND!r},'--tcp','--broker',str(session)]")
        tree=Imports().visit(ast.parse(src));ast.fix_missing_locations(tree)
        code=ast.unparse(tree)+'\n';compile(code,str(package/(name+'.py')),'exec')
        (package/(name+'.py')).write_text(code,encoding='utf-8')
    (package/'__init__.py').write_text(ENTRY,encoding='utf-8')
    (package/'module_properties.py').write_text(PROPERTIES,encoding='utf-8')
    output=stage/'out';output.mkdir()
    arguments=[sys.executable,'-m','nuitka','--mode=module','--include-package=yys_core','--nofollow-imports',
               '--msvc=latest','--jobs=4','--lto=no','--no-pyi-file','--assume-yes-for-downloads',
               '--output-dir='+str(output),'--report='+str(stage/'compilation-report.xml'),str(package)]
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'release_tools/build_deps')
    env['NUITKA_CACHE_DIR']=str(ROOT/'release_tools/compiler-cache')
    (stage/'build-info.json').write_text(json.dumps({'sources':FILES,'command':arguments},indent=2),encoding='utf-8')
    print('Build staging: '+str(stage),flush=True)
    process=subprocess.run(arguments,cwd=stage,env=env)
    if process.returncode:sys.exit(process.returncode)
    binaries=list(output.glob('yys_core*.pyd'))
    if len(binaries)!=1:raise RuntimeError('Expected one compiled core')
    result={'stage':str(stage),'binary':str(binaries[0]),'modules':len(FILES)+2}
    (ROOT/'release_tools/latest-compiled.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
