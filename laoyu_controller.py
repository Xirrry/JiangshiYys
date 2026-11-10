"""Private-profile game launch through LaoYu Pro; owns only its game's Job."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import _winapi
import proxy_support
import game_preferences
from laoyu_support import Client,LaoYuError
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'proxy-engine-experiment'))
from trial_job import OwnedJob
from game_tcp_trial import kernel,stamp,alive,ensure_owned_exit,write

def run(role_id,proxy_id,ticket,port,preferences=None):
    if uuid.UUID(ticket).hex!=ticket:raise ValueError('Invalid ticket')
    folder=ROOT/'data/laoyu-sessions';folder.mkdir(parents=True,exist_ok=True)
    file=folder/(ticket+'.json');cancel=file.with_suffix('.cancel')
    report={'phase':'starting','provider':'laoyu','role_id':role_id,'main_pid':None}
    save=lambda:write(file,report)
    save();hp=ht=job=None;k=kernel()
    def check_cancel():
        if cancel.exists():raise LaoYuError('代理启动已取消')
    try:
        loader=importlib.machinery.SourceFileLoader('laoyu_business',str(ROOT/'launcher.pyw'))
        spec=importlib.util.spec_from_loader(loader.name,loader);app=importlib.util.module_from_spec(spec);loader.exec_module(app)
        cfg=app.read_json(ROOT/'data/accounts.json',{})
        role=next(a for a in cfg.get('accounts',[]) if a['id']==role_id)
        if not role.get('confirmed') or role.get('proxy_id')!=proxy_id:raise LaoYuError('角色或代理绑定已变化，请刷新重试')
        profile=app.account_folder(ROOT/'data/profiles',role_id)
        old=app.read_json(profile/'running.json',{})
        if old.get('pid') and app.process_stamp(old['pid'])==old.get('stamp'):raise LaoYuError('角色已在运行')
        check_cancel();client=Client(port)
        report['phase']='syncing_proxy';save()
        line=client.ensure_line(proxy_support.ProxyStore(ROOT).spec(proxy_id))
        check_cancel();game,exe=app.find_game(cfg['game']);profile,cwd,env=app.prepare(ROOT/'data/profiles',game,role_id) if preferences is None else app.prepare(ROOT/'data/profiles',game,role_id,game_preferences.normalize(preferences))
        job=OwnedJob('Local\\YysLaoYu-'+ticket,create=True)
        command=str(cwd/exe.relative_to(game))
        hp,ht,pid,_=_winapi.CreateProcess(command,subprocess.list2cmdline([command]),None,None,False,4|0x400,env,str(cwd),subprocess.STARTUPINFO())
        job.assign(W.HANDLE(hp));created=stamp(k,W.HANDLE(hp))
        report.update(phase='binding_proxy',main_pid=pid);save()
        app.write_json(profile/'running.json',{'pid':pid,'stamp':created,'proxy_provider':'laoyu','proxy_ticket':ticket})
        check_cancel();client.bind(pid,line);check_cancel()
        if k.ResumeThread(W.HANDLE(ht))==0xffffffff:raise LaoYuError('无法恢复游戏运行')
        _winapi.CloseHandle(ht);ht=None
        report.update(phase='running_laoyu',line_confirmed=True,family_processes=job.count());save()
        while alive(k,W.HANDLE(hp)):
            check_cancel()
            if not client.bound(pid,line):raise LaoYuError('老鱼连接或 PID 线路绑定已失效，正在关闭角色')
            report['family_processes']=job.count();save();time.sleep(1)
        report['phase']='game_exited'
    except Exception as error:
        message=str(error) if isinstance(error,LaoYuError) else '老鱼代理启动异常，已阻止游戏继续运行；请检查配置后重试'
        report.update(phase='cancelled' if cancel.exists() else 'failed',message=message,error_type=type(error).__name__)
    finally:
        if job:job.stop_and_wait(report,save)
        if hp:ensure_owned_exit(k,W.HANDLE(hp),report,save)
        if ht:_winapi.CloseHandle(ht)
        if hp:_winapi.CloseHandle(hp)
        if job:job.close()
        save()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--role',required=True);p.add_argument('--proxy',required=True);p.add_argument('--ticket',required=True);p.add_argument('--port',type=int,default=22999);p.add_argument('--game-prefs');a=p.parse_args()
    run(a.role,a.proxy,a.ticket,a.port,json.loads(a.game_prefs) if a.game_prefs else None)
