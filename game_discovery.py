"""Bounded, read-only game discovery. Never searches whole drives or starts games."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import role_reader


def running_paths():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    for pid in role_reader.game_pids():
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:continue
        try:
            size=wintypes.DWORD(32768);buffer=ctypes.create_unicode_buffer(size.value)
            if kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)):
                file=Path(buffer.value)
                if file.name.lower() in ('onmyoji.exe','onmyoji_future.exe'):yield str(file)
        finally:kernel.CloseHandle(handle)


def registry_paths():
    import winreg
    uninstall=r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    def value(key,name):
        try:return str(winreg.QueryValueEx(key,name)[0])
        except OSError:return ''
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,uninstall,0,winreg.KEY_READ|view) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent,winreg.EnumKey(parent,index)) as key:
                                name=value(key,'DisplayName').lower()
                                if '阴阳师' not in name and 'onmyoji' not in name:continue
                                location=os.path.expandvars(value(key,'InstallLocation').strip().strip('"'))
                                if location:yield location
                                icon=os.path.expandvars(value(key,'DisplayIcon').strip())
                                match=re.match(r'^"([^"]+)"',icon)
                                icon=match[1] if match else re.sub(r',\s*-?\d+$','',icon).strip()
                                if icon:
                                    file=Path(icon);yield str(file);yield str(file.parent)
                        except OSError:continue
            except OSError:continue


def common_paths():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetLogicalDrives.restype=wintypes.DWORD
    kernel.GetDriveTypeW.argtypes=[wintypes.LPCWSTR];kernel.GetDriveTypeW.restype=wintypes.UINT
    mask=kernel.GetLogicalDrives()
    locations=('Game/yys','Games/yys','game/阴阳师','Games/阴阳师','yys','阴阳师','Onmyoji',
               'NetEase/阴阳师','Netease/Onmyoji','Program Files/Onmyoji','Program Files (x86)/Onmyoji',
               'Program Files/阴阳师','Program Files (x86)/阴阳师','App/yys','App/阴阳师')
    for index in range(26):
        if mask&(1<<index):
            drive=chr(65+index)+':\\'
            # Fixed local drives only: no removable, optical or disconnected network disks.
            if kernel.GetDriveTypeW(drive)==3:
                for relative in locations:yield str(Path(drive)/relative)


def discover(find_game,current='',providers=None):
    found={};current_valid=False
    def add(value,source):
        if not value:return False
        try:
            # Resolve junctions so an isolated game's shared bin points to the real install.
            game,exe=find_game(str(value))
            exe=Path(exe).resolve();game,exe=find_game(str(exe))
            path=str(game);key=os.path.normcase(path)
            if key not in found:found[key]={'path':path,'executable':str(exe),'sources':[]}
            if source not in found[key]['sources']:found[key]['sources'].append(source)
            return True
        except (OSError,ValueError,RuntimeError):return False
    current_valid=add(current,'当前配置')
    for label,provider in providers if providers is not None else (
        ('运行中的游戏',running_paths),('系统安装记录',registry_paths),('常见安装位置',common_paths)):
        try:
            for path in provider():add(path,label)
        except OSError:continue
    return {'current_valid':current_valid,'candidates':list(found.values())}
