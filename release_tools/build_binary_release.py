"""Build a source-free native-core portable distribution; no cleanup/delete calls."""
import importlib._bootstrap_external
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION=json.loads((ROOT/'brand.json').read_text(encoding='utf-8'))['version']
SKIP={'__pycache__','site-packages','test','tests','idlelib','ensurepip','venv','.git','node_modules'}

def copy(src,dst):
    if src.is_symlink() or src.is_junction() or not src.is_file():raise RuntimeError('Unsafe/missing input: '+str(src))
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)

def files(base):
    for folder,dirs,names in os.walk(base,followlinks=False):
        parent=Path(folder)
        dirs[:]=[d for d in dirs if d not in SKIP and not (parent/d).is_symlink() and not (parent/d).is_junction()]
        for name in names:
            path=parent/name
            if path.suffix.lower() not in {'.pyc','.pyo','.log'}:yield path,path.relative_to(base)

def bytecode(source,name):
    return importlib._bootstrap_external._code_to_timestamp_pyc(compile(source,name,'exec',dont_inherit=True),mtime=0,source_size=0)

def main():
    compiled=json.loads((ROOT/'release_tools/latest-compiled.json').read_text(encoding='utf-8'))
    batch=ROOT/'releases'/('v'+VERSION+'-binary-'+time.strftime('%Y%m%d-%H%M%S'));batch.mkdir(parents=True,exist_ok=False)
    channel=json.loads((ROOT/'brand.json').read_text(encoding='utf-8')).get('release_channel','stable')
    local_build=json.loads((ROOT/'brand.json').read_text(encoding='utf-8')).get('local_build',False)
    suffix='-local-test' if local_build else '-experimental' if channel=='experimental' else ''
    package=batch/('JiangshiYys-'+VERSION+suffix+'-win-x64');package.mkdir()
    for name in ['brand.json','servers.json','server-merges.json','官方合区关系说明.md','用户使用手册.md','用户使用手册.html','运行环境说明.md','发布说明.md','第三方组件说明.md']:
        copy(ROOT/name,package/name)
    copy(Path(compiled['binary']),package/'yys_core.pyd')
    copy(ROOT/'hardware/mail-reader/mail_agent.dll',package/'hardware/mail-reader/mail_agent.dll')
    copy(ROOT/'hardware/IdentityView.dll',package/'hardware/IdentityView.dll')
    copy(ROOT/'hardware/MinHook-LICENSE.txt',package/'hardware/MinHook-LICENSE.txt')
    for name in ['app-icon.png','app-icon.ico']:copy(ROOT/'assets'/name,package/'assets'/name)
    entry=ROOT/'frontend/dist/index.html';copy(entry,package/'frontend/dist/index.html')
    graph=json.loads((entry.parent/'.vite/manifest.json').read_text(encoding='utf-8'));assets=set()
    for row in graph.values():assets.add(row['file']);assets.update(row.get('css',[]));assets.update(row.get('assets',[]))
    for asset in assets:
        if not asset.startswith('assets/') or '..' in Path(asset).parts:raise RuntimeError('Invalid asset')
        copy(entry.parent/asset,package/'frontend/dist'/asset)
    # Compile dependencies to source-less Python bytecode. Only first-party code is native.
    for path,relative in files(ROOT/'vendor'):
        if relative.parts[0] in {'proxy_tools','proxy_tools-0.1.0.dist-info','bin'}:continue
        if any(p.endswith('.dist-info') for p in relative.parts):
            if path.name not in {'METADATA','WHEEL','top_level.txt'} and 'licenses' not in relative.parts:continue
        if path.suffix.lower() in {'.pyw','.c','.h','.ps1','.bat'}:continue
        target=package/'vendor'/relative
        if path.suffix=='.py':
            source=path.read_bytes()
            if relative.as_posix()=='webview/__init__.py':
                source=source.replace(b'from proxy_tools import module_property',b'from yys_core.module_properties import module_property')
            target=target.with_suffix('.pyc');target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(bytecode(source,'vendor/'+relative.as_posix()))
        else:copy(path,target)
    runtime=package/'runtime';python=Path(sys.base_prefix)
    for name in ['python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        copy(python/name,runtime/name)
    # Store bytecode uncompressed inside the inner ZIP so bootstrap never needs zlib.
    with zipfile.ZipFile(runtime/'python312.zip','w',zipfile.ZIP_STORED) as archive:
        for path,relative in files(python/'Lib'):
            if path.suffix=='.py':archive.writestr(relative.with_suffix('.pyc').as_posix(),bytecode(path.read_bytes(),'stdlib/'+relative.as_posix()))
            else:archive.write(path,relative.as_posix())
    for directory in ['DLLs','tcl']:
        for path,relative in files(python/directory):
            if path.suffix.lower() not in {'.py','.pyw','.c','.h','.ps1','.bat'}:copy(path,runtime/directory/relative)
    (runtime/'python312._pth').write_text('.\nDLLs\npython312.zip\n..\n../vendor\n',encoding='ascii')
    engine=package/'proxy-engine-experiment'
    for name in ['YysProxyCore.dll','WinDivert.dll','WinDivert64.sys']:copy(ROOT/'proxy-engine-experiment/bin'/name,engine/'bin'/name)
    copy(ROOT/'proxy-engine-experiment/ProxyBridge-LICENSE.txt',engine/'ProxyBridge-LICENSE.txt')
    copy(ROOT/'proxy-engine-experiment/windivert/LICENSE',package/'third-party/WinDivert-LICENSE.txt')
    downloads=Path(r'C:/Users/Xir/.codex/visualizations/2026/11/08/01a1ba01-539c-7f42-ac5e-c5e2a6a7e013/release-prep/third-party')
    for name in ['WebView2-LICENSE.txt','WebView2-NOTICE.txt','WinDivert-v2.2.2-source.zip']:copy(downloads/name,package/'third-party'/name)
    copy(ROOT/'frontend/node_modules/vue/LICENSE',package/'third-party/Vue-LICENSE.txt')
    for name in ['LICENSE.txt','LICENSE-RUNTIME.txt','NOTICE.txt']:
        copy(ROOT/'release_tools/build_deps/nuitka-4.3.5.dist-info/licenses'/name,package/'third-party'/('Nuitka-'+name))
    with zipfile.ZipFile(package/'third-party/ProxyBridge-modified-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for directory in ['src','windivert/include']:
            for path,relative in files(ROOT/'proxy-engine-experiment'/directory):archive.write(path,directory+'/'+relative.as_posix())
        for name in ['ProxyBridge-LICENSE.txt','source-manifest.json']:archive.write(ROOT/'proxy-engine-experiment'/name,name)
        archive.write(ROOT/'proxy-engine-experiment/windivert/x64/WinDivert.lib','windivert/x64/WinDivert.lib')
        sources=' '.join('"%~dp0src\\'+p.name+'"' for p in sorted((ROOT/'proxy-engine-experiment/src').glob('*.c')))
        rebuild='@echo off\ncl /nologo /utf-8 /O2 /D_CRT_SECURE_NO_WARNINGS /D_WINSOCK_DEPRECATED_NO_WARNINGS /DPROXYBRIDGE_EXPORTS /LD /I"%~dp0windivert\\include" '+sources+' /link /DYNAMICBASE /NXCOMPAT /LIBPATH:"%~dp0windivert\\x64" WinDivert.lib ws2_32.lib iphlpapi.lib advapi32.lib /OUT:"%~dp0YysProxyCore.dll"\n'
        archive.writestr('build-native.cmd',rebuild)
    # Compile the Windows GUI executable which invokes the native core, not a .py file.
    native=batch/'native-build';native.mkdir()
    c=(ROOT/'release_tools/native-source/launcher_bootstrap.c').read_text(encoding='utf-8')
    c=c.replace('app.pyw','yys_core.pyd')
    c=c.replace('L"\\\"%s\\\" -B \\\"%s\\\"",python,script', 'L"\\\"%s\\\" -B -c \\\"import yys_core; yys_core.main()\\\"",python')
    assert ' -B -c ' in c
    (native/'launcher_bootstrap.c').write_text(c,encoding='utf-8')
    for name in ['app.rc','app.ico','update_helper.c']:copy(ROOT/'release_tools/native-source'/name,native/name)
    command='@echo off\nchcp 65001 >nul\ncall "D:\\App\\Microsoft Visual Studio\\18\\Community\\VC\\Auxiliary\\Build\\vcvarsall.bat" x64 >nul\nif errorlevel 1 exit /b 1\ncd /d "%~dp0"\nrc /nologo /fo app.res app.rc\nif errorlevel 1 exit /b 1\ncl /nologo /utf-8 /O2 /W4 /MT /guard:cf launcher_bootstrap.c app.res /Fe"'+str(package/'僵尸痒痒鼠.exe')+'" /link user32.lib /SUBSYSTEM:WINDOWS /DYNAMICBASE /NXCOMPAT /HIGHENTROPYVA /MANIFEST:EMBED /MANIFESTUAC:"level=\'asInvoker\' uiAccess=\'false\'"\nexit /b %errorlevel%\n'
    (native/'build.cmd').write_text(command,encoding='utf-8',newline='\r\n')
    r=subprocess.run(['cmd','/c',str(native/'build.cmd')],cwd=native,capture_output=True)
    (batch/'native-build.log').write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('Native entry build failed')
    helper_command='@echo off\nchcp 65001 >nul\ncall "D:\\App\\Microsoft Visual Studio\\18\\Community\\VC\\Auxiliary\\Build\\vcvarsall.bat" x64 >nul\nif errorlevel 1 exit /b 1\ncd /d "%~dp0"\ncl /nologo /utf-8 /O2 /W4 /MT update_helper.c /Fe"'+str(package/'ApplyUpdate.exe')+'" /link shell32.lib user32.lib /SUBSYSTEM:WINDOWS /DYNAMICBASE /NXCOMPAT\nexit /b %errorlevel%\n'
    (native/'build-helper.cmd').write_text(helper_command,encoding='utf-8',newline='\r\n')
    helper_result=subprocess.run(['cmd','/c',str(native/'build-helper.cmd')],cwd=native,capture_output=True)
    (batch/'helper-build.log').write_bytes(helper_result.stdout+helper_result.stderr)
    if helper_result.returncode:raise RuntimeError('Update helper build failed')

    # Test an exact copy; distributable directory must remain pristine.
    smoke=batch/'smoke-test/app';shutil.copytree(package,smoke)
    test=ROOT/'release_tools/test_compiled_release.py'
    result=subprocess.run([str(smoke/'runtime/python.exe'),'-B','-c',test.read_text(encoding='utf-8')],cwd=smoke,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (batch/'binary-smoke.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('Compiled runtime self-test failed; inspect binary-smoke.txt')
    if subprocess.run([str(package/'僵尸痒痒鼠.exe'),'--check']).returncode:raise RuntimeError('EXE prerequisites failed')
    inventory={}
    for path in sorted(package.rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(package)
        if path.suffix.lower() in {'.py','.pyw','.c','.h','.ps1','.bat'}:raise RuntimeError('Plaintext executable/source in release: '+str(relative))
        if any(p in {'data','sessions','tickets','node_modules','__pycache__','test-results'} for p in relative.parts):raise RuntimeError('Private/runtime artifact in release: '+str(relative))
        if any(s in path.name for s in ['before-','desktop-error','desktop-health','laoyu-requests','proxy-trial-ui']):raise RuntimeError('Private artifact in release')
        inventory[relative.as_posix()]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (package/'release-manifest.json').write_text(json.dumps({'version':VERSION,'core':'native compiled PYD','files':inventory},ensure_ascii=False,indent=2),encoding='utf-8')
    archive=batch/(package.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(package.rglob('*')):
            if path.is_file():z.write(path,path.relative_to(batch))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (batch/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    report={'version':VERSION,'package':str(package),'zip':str(archive),'sha256':digest,'zip_bytes':archive.stat().st_size,
            'release_channel':channel,'local_build':local_build,'core_modules_compiled':compiled['modules'],'plaintext_application_sources':False,'user_data_included':False,
            'binary_smoke':'passed','ui_smoke':'pending','public_upload':'not performed','cross_machine_game_test':'not performed'}
    (batch/'release-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'release_tools/latest-binary-release.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
