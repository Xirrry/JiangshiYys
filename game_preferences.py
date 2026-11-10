"""Verified desktop-client settings; apply only to private profiles before launch."""
import copy
import json
from pathlib import Path
import uuid

DEFAULTS={'mute_all':True,'skip_intro':True,'lowest_graphics':True}
LOW_VALUES={k:0 for k in ('frame_rate','render_scale','shadow','shader','post_process','msaa',
    'ssl_light','scene_detail','effect','reflection','outline','unreal','hd_font','ui_effect')}

def normalize(prefs=None):
    if prefs is None:prefs={}
    if not isinstance(prefs,dict):raise ValueError('游戏设置格式无效')
    result={**DEFAULTS,**{k:v for k,v in prefs.items() if k in DEFAULTS}}
    if any(type(v) is not bool for v in result.values()):raise ValueError('游戏设置开关必须为布尔值')
    return result

def overrides(prefs=None):
    if prefs is None:return {}
    if not isinstance(prefs,dict):raise ValueError('游戏覆盖设置格式无效')
    result={}
    for key,value in prefs.items():
        if key not in DEFAULTS:continue
        if value is None:continue
        if type(value) is not bool:raise ValueError('覆盖设置需选择继承、强制设置或不强制')
        result[key]=value
    return result

def resolve(config,role_id,plan=None):
    result=normalize(config.get('game_preferences'))
    role=next((x for x in config.get('accounts',[])+config.get('pending',[]) if x.get('id')==role_id),{})
    result.update(overrides(role.get('game_preferences')))
    result.update(overrides(plan))
    return result

def patch(data,prefs=None):
    if not isinstance(data,dict):raise ValueError('游戏配置不是对象，未修改')
    flags=normalize(prefs);result=copy.deepcopy(data)
    if flags['mute_all']:
        result.update(voiceState=False,sfxSoundState=False,VideoSoundState=False,yuyinState=False,
                      MusicVolume=0.0,SfxSoundVolume=0.0,VideoSoundVolume=0.0,yuyinVolume=0.0)
    if flags['skip_intro']:
        # Confirmed by toggling the game's 登录动画 UI: True means OFF.
        result['launchVideoState']=True
    if flags['lowest_graphics']:
        old=result.get('graphics_quality_state',{})
        if not isinstance(old,dict) or (old.get('version',3)!=3):
            raise ValueError('当前画质配置版本尚未支持，请关闭最低画质选项后重试')
        values=old.get('values',{})
        if not isinstance(values,dict):raise ValueError('画质细项格式无效，未修改')
        result['graphics_quality_state']={**old,'version':3,'preset':'very_low','values':{**values,**LOW_VALUES}}
        # The game's very_low preset still enables AA. Explicitly disable both stores.
        result['msaa_switch']=False
    return result

def apply(file,profiles_root,prefs=None):
    flags=normalize(prefs)
    if not any(flags.values()):return False
    file=Path(file).absolute();base=Path(profiles_root).absolute()
    if not file.is_relative_to(base):raise ValueError('拒绝修改角色目录外的游戏配置')
    for current in (file,*file.parents):
        if current.is_symlink() or current.is_junction():raise ValueError('游戏设置配置路径不能包含链接')
        if current==base:break
    if not file.resolve().is_relative_to(base.resolve()):raise ValueError('游戏设置路径超出私有角色目录')
    if file.exists() and (not file.is_file() or file.stat().st_nlink>1):raise ValueError('拒绝修改共享的游戏配置')
    raw=file.read_bytes() if file.exists() else None
    hexadecimal=True
    if raw is None:data={}
    else:
        text=raw.decode('utf-8-sig')
        try:data=json.loads(text);hexadecimal=False
        except json.JSONDecodeError:
            try:data=json.loads(bytes.fromhex(text))
            except (ValueError,UnicodeError):raise ValueError('游戏配置无法解析，未覆盖原文件') from None
    result=patch(data,flags)
    if json.dumps(data,sort_keys=True)==json.dumps(result,sort_keys=True):return False
    file.parent.mkdir(parents=True,exist_ok=True)
    if raw is not None:
        backup=file.with_name(file.name+'.before-launch-settings')
        if backup.is_symlink() or backup.is_junction():raise ValueError('游戏设置备份路径无效')
        if not backup.exists():
            with backup.open('xb') as stream:stream.write(raw)
    text=json.dumps(result,ensure_ascii=False,separators=(',',':'))
    if hexadecimal:text=text.encode('utf-8').hex()
    tmp=file.with_name(file.name+'.launch-settings-'+uuid.uuid4().hex+'.tmp')
    with tmp.open('x',encoding='utf-8') as stream:stream.write(text)
    tmp.replace(file)
    return True
