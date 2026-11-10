"""Vue desktop bridge. Existing profiles stay on disk; only explicit actions write."""
import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import threading
import time
import uuid
import subprocess
import sys
import pinganzhi_sync
import role_reader
import window_layout
import proxy_support
import proxy_dns
import laoyu_support
import game_preferences
import game_discovery
import profile_cleanup
import device_identity
import app_updates

ROOT = Path(__file__).resolve().parent


class DesktopApi:
    def __init__(self, data_root=None):
        loader = importlib.machinery.SourceFileLoader('desktop_business', str(ROOT / 'launcher.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self._app = importlib.util.module_from_spec(spec)
        loader.exec_module(self._app)
        self._root = Path(data_root or ROOT)
        self._app.DATA = self._root / 'data'
        self._app.CONFIG = self._app.DATA / 'accounts.json'
        self._lock = threading.RLock()
        self._logs = []
        self._sources = {}
        self._backed_up = False
        self._children = []
        self._launch_status = {}
        self._cleanup_plans = {}
        self._device_sessions = {}
        self._updates = app_updates.UpdateManager(self._root, json.loads((ROOT / "brand.json").read_text(encoding="utf-8")))
        self._allow_close = False
        self._proxies = proxy_support.ProxyStore(self._root)
        self._note('Vue 桌面版已就绪，原有角色、分组和排列方案已保留。')

    def _config(self):
        cfg = self._app.read_json(self._app.CONFIG, {'game': 'D:/Game/yys', 'accounts': [], 'pending': []})
        cfg.setdefault('pending', [])
        return cfg

    def _save(self, cfg):
        if not self._backed_up and self._app.CONFIG.exists():
            shutil.copy2(self._app.CONFIG, self._app.CONFIG.with_name(f'accounts.before-vue-{time.time_ns()}.json'))
            self._backed_up = True
        self._app.write_json(self._app.CONFIG, cfg)

    def _note(self, message):
        self._logs.append({'time': time.strftime('%H:%M:%S'), 'message': str(message)})
        self._logs = self._logs[-150:]

    def _roles(self):
        cfg = self._config()
        return cfg['accounts'] + cfg['pending']

    def _ids(self, ids):
        known = {a['id'] for a in self._roles()}
        if not isinstance(ids, list) or len(ids) != len(set(ids)) or any(i not in known for i in ids):
            raise ValueError('角色列表已变化，请刷新后重试')
        return ids

    def _state(self, key):
        return self._app.read_json(self._app.account_folder(self._app.DATA / 'profiles', key) / 'running.json', {})

    def _running(self, state):
        try:
            return bool(state.get('pid') and self._app.process_stamp(state['pid']) == state.get('stamp'))
        except OSError:
            return False

    def snapshot(self):
        with self._lock:
            cfg = self._config()
            tracked = {a['id']: self._state(a['id']) for a in cfg['accounts'] + cfg['pending']}
            states = {key:{'running':self._running(state),'pid':state.get('pid')} for key,state in tracked.items()}
            devices = self._device_summaries(tracked)
            routes = self._proxy_routes()
            bound = {a['id'] for a in cfg['accounts']+cfg['pending'] if a.get('proxy_id')}
            for key, route in routes.items():
                if key in bound and not route.get('active') and not states.get(key,{}).get('running'):
                    if route.get('phase')=='failed':
                        self._launch_status[key]={**self._launch_status.get(key,{}),'phase':'failed','error':route.get('message') or '代理组件异常，角色已关闭，请检查代理后重试'}
                    elif route.get('phase')=='cancelled':
                        self._launch_status[key]={**self._launch_status.get(key,{}),'phase':'cancelled','error':''}
            return {'config': cfg, 'states': states, 'devices': devices, 'screens': window_layout.screens(), 'logs': self._logs,
                    'proxies': self._proxies.public(), 'proxy_engine': {'ready': True, 'backend': cfg.get('proxy_backend','builtin'), 'laoyu_port': cfg.get('laoyu_port',22999), 'laoyu_hidden': self._proxies.hidden_laoyu(cfg.get('laoyu_port',22999)), 'mode': 'tcp', 'capacity': None if cfg.get('proxy_backend')=='laoyu' else 1, 'message': '由老鱼专业版执行代理，线路和进程绑定在启动前确认' if cfg.get('proxy_backend')=='laoyu' else '内置 TCP 代理：同时支持 1 个代理角色，DNS 接管未启用', 'trial': self._proxy_trial_status(), 'routes': routes}, 'launches': copy.deepcopy(self._launch_status), 'updates': self._updates.status(), 'version': 'v9.49', 'source_root': str(pinganzhi_sync.default_root())}

    def update(self, action='status', payload=None):
        try:
            if action == 'startup':
                data = self._updates.start('check') if self._updates.auto else self._updates.status()
            elif action in ('check', 'download'):
                data = self._updates.start(action)
            elif action == 'settings':
                data = self._updates.settings((payload or {}).get('auto_check'))
            elif action == 'page':
                data = self._updates.open_page()
            elif action == 'folder':
                data = self._updates.open_download()
            elif action == 'status':
                data = self._updates.status()
            else:
                raise ValueError('不支持的更新操作')
            return {'ok': True, 'data': data}
        except Exception as error:
            return {'ok': False, 'error': str(error)}

    def choose_folder(self):
        import webview
        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None

    def command(self, action, payload=None):
        operations = {'game': self._game, 'device_profile': self._device_profile, 'device_check': self._device_check, 'detect_game': self._detect_game, 'delete_removed': self._delete_removed, 'inspect_removed': self._inspect_removed, 'game_preferences': self._game_preferences, 'group': self._group, 'save_plan': self._save_plan,
                      'delete_plan': self._delete_plan, 'window': self._window, 'preview': self._preview,
                      'arrange': self._arrange, 'restore': self._restore, 'close': self._close,
                      'start': self._start, 'add': self._add, 'read': self._read, 'confirm': self._confirm,
                      'scan_sync': self._scan_sync, 'sync': self._sync, 'reset_legacy': self._reset_legacy, 'role_meta': self._role_meta,
                      'remove_roles': self._remove_roles, 'restore_role': self._restore_role, 'single_start': self._single_start, 'plan_order': self._plan_order, 'finish_close': self._finish_close, 'role_view': self._role_view, 'close_plan': self._close_plan, 'start_member': self._start_member, 'member_view': self._member_view, 'proxy_save': self._proxy_save, 'proxy_delete': self._proxy_delete, 'laoyu_restore': self._laoyu_restore, 'proxy_test': self._proxy_test, 'proxy_bind': self._proxy_bind, 'proxy_trial_start': self._proxy_trial_start, 'proxy_backend': self._proxy_backend, 'laoyu_probe': self._laoyu_probe, 'laoyu_sync': self._laoyu_sync, 'proxy_dns_test': self._proxy_dns_test, 'launch_preflight': self._launch_preflight}
        try:
            if action not in operations:
                raise ValueError('不支持的操作')
            if action in ('proxy_test', 'proxy_dns_test', 'laoyu_probe', 'laoyu_sync', 'detect_game', 'device_check'):
                return {'ok': True, 'data': operations[action](payload or {})}
            with self._lock:
                return {'ok': True, 'data': operations[action](payload or {})}
        except Exception as error:
            return {'ok': False, 'error': str(error)}

    def _device_session_alive(self, key):
        session = self._device_sessions.get(key)
        return session is not None and not session.process_ended()

    def _device_summaries(self, tracked):
        for key, session in list(self._device_sessions.items()):
            if session.process_ended():
                session.release_handles()
                self._device_sessions.pop(key, None)
        summaries = {}
        for role in self._roles():
            key = role['id']
            profile = role.get('device_identity')
            state = tracked.get(key,{})
            session = self._device_sessions.get(key)
            phase = 'off'
            if isinstance(profile,dict) and profile.get('enabled') is True:
                if session and session.pid==state.get('pid') and session.stamp==state.get('stamp'):
                    phase = 'loaded'
                elif self._running(state):
                    phase = 'unverified'
                else:
                    phase = 'configured'
            summaries[key] = {'phase':phase,'pid':state.get('pid'),'stamp':str(state.get('stamp') or '')}
        return summaries

    def _device_check(self, p):
        with self._lock:
            key = self._ids([p.get('id')])[0]
            role = next(r for r in self._roles() if r['id']==key)
            state = self._state(key)
            profile = role.get('device_identity')
            if not isinstance(profile,dict) or profile.get('enabled') is not True:
                return {'phase':'off','pid':state.get('pid'),'stamp':str(state.get('stamp') or '')}
            session = self._device_sessions.get(key)
            if not session or session.pid!=state.get('pid') or session.stamp!=state.get('stamp'):
                return {'phase':'unverified' if self._running(state) else 'configured','pid':state.get('pid'),'stamp':str(state.get('stamp') or ''),'hint':'当前启动器没有这个窗口的加载记录。需要核验时，请退出角色后从当前启动器重新启动。'}
            if session.process_ended():
                session.release_handles()
                self._device_sessions.pop(key,None)
                return {'phase':'configured','pid':state.get('pid'),'stamp':str(state.get('stamp') or '')}
        try:
            # On demand only, outside the main UI/config lock; no polling thread injection.
            status = session.read_status()
        except (OSError,ValueError):
            return {'phase':'check_failed','pid':state.get('pid'),'stamp':str(state.get('stamp') or ''),'error':'当前窗口状态核验失败，不能确认组件仍在启用。'}
        with self._lock:
            current = self._state(key)
            if self._device_sessions.get(key) is not session or current.get('pid')!=session.pid or current.get('stamp')!=session.stamp or session.process_ended():
                return {'phase':'unverified','pid':current.get('pid'),'stamp':str(current.get('stamp') or ''),'hint':'核验期间窗口已变化，旧结果已忽略，请刷新后重试。'}
        return {'phase':'checked' if status.get('active') else 'component_inactive','pid':session.pid,'stamp':str(session.stamp),'api_calls':status.get('api_calls',[]),'checked_at':time.time()}

    def _device_profile(self, p):
        key = self._ids([p.get('id')])[0]
        if self._running(self._state(key)) or self._device_session_alive(key) or self._proxy_routes().get(key,{}).get('active'):
            raise ValueError('请先退出角色及代理会话，再生成设备参数')
        return device_identity.new_profile()

    def _activate_device(self, key, role):
        profile = device_identity.normalize(role.get('device_identity'))
        if not profile or not profile['enabled']:
            return
        state = self._state(key)
        old = self._device_sessions.get(key)
        if old and old.pid==state.get('pid') and old.stamp==state.get('stamp'):
            return
        if old:
            old.release_handles()
        self._device_sessions[key] = device_identity.Session(ROOT,state,profile,self._app.process_stamp)
        self._note('已启用实验性设备接口视图；不代表完整硬件身份隔离。')

    def _game_preferences(self, p):
        prefs = game_preferences.normalize(p)
        cfg = self._config()
        cfg['game_preferences'] = prefs
        self._save(cfg)
        self._note('游戏启动设置已保存，将在角色下次启动前应用。')
        return prefs

    def _detect_game(self, p):
        automatic = p.get('automatic') is True
        with self._lock:
            original = self._config().get('game', '')
        # Startup does not rescan or replace an already valid user configuration.
        if automatic:
            try:
                if original:
                    game, exe = self._app.find_game(original)
                    return {'current_valid': True, 'candidates': [{'path':str(game), 'executable':str(exe), 'sources':['当前配置']}], 'saved':False}
            except (OSError, ValueError):
                pass
        result = game_discovery.discover(self._app.find_game, original)
        result['saved'] = False
        with self._lock:
            cfg = self._config()
            if automatic and not result['current_valid'] and len(result['candidates']) == 1 and cfg.get('game', '') == original:
                cfg['game'] = result['candidates'][0]['path']
                self._save(cfg)
                result['saved'] = True
                self._note('已自动检测并保存游戏安装目录。')
        return result

    def _game(self, p):
        game, exe = self._app.find_game(p['path'])
        cfg = self._config()
        cfg['game'] = str(game)
        self._save(cfg)
        return str(game)

    def _group(self, p):
        cfg = self._config()
        kind, name = p['kind'], str(p.get('name', '')).strip()
        if not name:
            raise ValueError('请填写分组名称')
        groups = set(cfg.get('groups', []))
        if kind == 'new':
            groups.add(name)
        elif kind in ('rename', 'remove'):
            if name == '未分组':
                raise ValueError('默认分组不能重命名或取消')
            new = str(p.get('new', '')).strip() if kind == 'rename' else '未分组'
            if not new:
                raise ValueError('请填写新名称')
            groups.discard(name)
            groups.add(new)
            for a in cfg['accounts'] + cfg['pending']:
                if a.get('group') == name:
                    a['group'] = new
        elif kind == 'assign':
            ids = self._ids(p['ids'])
            groups.add(name)
            for a in cfg['accounts'] + cfg['pending']:
                if a['id'] in ids:
                    a['group'] = name
        else:
            raise ValueError('无效的分组操作')
        cfg['groups'] = sorted(groups)
        self._save(cfg)

    def _layout(self, p):
        ids = self._ids(p.get('ids', []))
        settings = dict(p.get('settings') or {})
        profiles = p['profiles'] if 'profiles' in p else self._config().get('window_profiles', {})
        screens = window_layout.screens()
        screen = next((s for s in screens if s['id'] == p.get('screen')), screens[0] if screens else None)
        if not screen:
            raise ValueError('没有可用显示器')
        frame = (0, 0)
        for key in ids:
            try:
                frame = window_layout.border(self._state(key), self._app.process_stamp)
                break
            except (OSError, ValueError):
                pass
        rects = window_layout.profile_rectangles(ids, screen['work'], profiles, frame=frame, **settings)
        return ids, rects, screen['work'], frame

    def _preview(self, p):
        ids, rects, work, frame = self._layout(p)
        return {'rects': rects, 'work': work, 'frame': frame}

    @staticmethod
    def _launch_delay(value):
        import math
        if isinstance(value, bool):
            raise ValueError('启动间隔需为 0～300 秒')
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            raise ValueError('启动间隔需为 0～300 秒') from None
        if not math.isfinite(seconds) or not 0 <= seconds <= 300:
            raise ValueError('启动间隔需为 0～300 秒')
        return seconds

    def _save_plan(self, p):
        self._layout(p)
        name = str(p.get('name', '')).strip()
        if not name:
            raise ValueError('请填写方案名称')
        cfg = self._config()
        cfg.setdefault('layout_plans', {})[name] = {'settings': p['settings'], 'roles': p['ids'],
            'windows': {key: value for key, value in p.get('profiles', {}).items() if key in p['ids']}, 'screen_device': p.get('screen'), 'auto': bool(p.get('auto')), 'launch_delay': self._launch_delay(p.get('launch_delay', 0)), 'game_preferences':game_preferences.overrides(p.get('game_preferences'))}
        self._save(cfg)
        self._note(f'已保存排列方案：{name}')

    def _plan_order(self, p):
        cfg = self._config()
        order = p.get('names')
        known = set(cfg.get('layout_plans', {}))
        if not isinstance(order, list) or any(not isinstance(n, str) for n in order) or len(order) != len(set(order)) or set(order) != known:
            raise ValueError('方案列表已变化，请刷新后重新排序')
        cfg['plan_order'] = list(order)
        self._save(cfg)
        return order

    def _delete_plan(self, p):
        cfg = self._config()
        cfg.setdefault('layout_plans', {}).pop(p['name'], None)
        self._save(cfg)

    def _window(self, p):
        self._layout(p)
        cfg = self._config()
        known = {a['id'] for a in self._roles()}
        profiles = {key: {k: int(v) for k, v in value.items() if k in ('x', 'y', 'width', 'height')}
                    for key, value in p.get('profiles', {}).items() if key in known}
        cfg['window_profiles'] = profiles
        self._save(cfg)

    def _arrange(self, p):
        ids, rects, work, frame = self._layout(p)
        cfg = self._config()
        positions = cfg.setdefault('last_window_positions', {})
        count = 0
        for key in ids:
            try:
                positions[key] = window_layout.act(self._state(key), self._app.process_stamp, rectangle=rects[key])
                count += 1
            except (OSError, ValueError):
                pass
        if not count:
            raise ValueError('所选角色没有已出现的、由本工具跟踪的游戏窗口')
        self._save(cfg)
        self._note(f'已排列 {count} 个游戏窗口')
        return count

    def _restore(self, p):
        count = 0
        for key, rect in self._config().get('last_window_positions', {}).items():
            if key not in {a['id'] for a in self._roles()}:
                continue
            try:
                window_layout.act(self._state(key), self._app.process_stamp, rectangle=rect)
                count += 1
            except (OSError, ValueError):
                pass
        self._note(f'已恢复 {count} 个窗口位置')
        return count

    def _close_plan(self, p):
        cfg = self._config()
        name = p.get('name')
        if not isinstance(name, str) or name not in cfg.get('layout_plans', {}):
            raise ValueError('启动方案已不存在，请刷新后重试')
        known = {a['id'] for a in cfg['accounts'] + cfg['pending']}
        ids = list(dict.fromkeys(key for key in cfg['layout_plans'][name].get('roles', []) if key in known))
        return self._close({'ids': ids, 'force': bool(p.get('force'))})

    def _close(self, p):
        ids = self._ids(p['ids'])
        count = 0
        routes = self._proxy_routes()
        for key in ids:
            trial = routes.get(key,{})
            try:
                if trial.get('active'):
                    ticket = trial.get('ticket')
                    if ticket:
                        cancel = (self._root / 'data/laoyu-sessions' if trial.get('provider')=='laoyu' else ROOT / 'proxy-engine-experiment/tickets') / (ticket + '.cancel')
                        cancel.parent.mkdir(exist_ok=True)
                        cancel.write_text('cancel', encoding='ascii')
                        self._launch_status[key]={**self._launch_status.get(key,{}),'phase':'cancelled','error':''}
                    if not self._running(self._state(key)):
                        count += 1
                        continue
                if p.get('force'):
                    if window_layout.terminate_tracked(self._state(key)):
                        count += 1
                        self._launch_status[key]={**self._launch_status.get(key,{}),'phase':'cancelled','error':''}
                else:
                    window_layout.act(self._state(key), self._app.process_stamp, close=True)
                    count += 1
            except (OSError, ValueError):
                pass
        self._note(f'已请求关闭或取消 {count} 个角色' if p.get('force') else f'已向 {count} 个已跟踪窗口发送正常关闭请求')
        return count

    def _launch_result(self, key, phase, error, options):
        current = self._launch_status.get(key,{})
        expected = options.get('request_id')
        if current.get('request_id') != expected:
            return False
        if current.get('phase')=='cancelled' and phase!='cancelled':
            return False
        row = {'phase':phase,'error':error}
        if expected:
            row['request_id']=expected
        self._launch_status[key]=row
        return True

    def _title_later(self, key, options):
        for attempt in range(25):
            try:
                with self._lock:
                    current = self._launch_status.get(key,{})
                    if current.get('request_id')!=options.get('request_id') or current.get('phase')=='cancelled':
                        return
                    role = next(a for a in self._roles() if a['id']==key)
                    title = (role.get('nickname') or role.get('name','阴阳师')) + (' · '+role['server'] if role.get('server') else '')
                    window_layout.act(self._state(key), self._app.process_stamp, title=title)
                    if options.get('single'):
                        ids, rects, work, frame = self._layout({**options,'ids':options.get('layout_ids',options['ids'])})
                        window_layout.act(self._state(key), self._app.process_stamp, rectangle=rects[key])
                    elif options.get('auto') and role.get('confirmed'):
                        self._arrange({**options,'ids':options.get('layout_ids',options['ids'])})
                    try:
                        self._activate_device(key, role)
                    except Exception:
                        self._close({'ids':[key],'force':True})
                        self._launch_status[key]={'phase':'failed','error':'设备实验初始化失败，已关闭该角色；可关闭实验设置后重试','request_id':options.get('request_id')}
                        return
                    self._launch_result(key,'ready','',options)
                    return
            except (OSError, ValueError, StopIteration):
                time.sleep(2)
        with self._lock:
            self._launch_result(key,'failed','游戏窗口未就绪或尺寸设置失败，请检查游戏窗口后重试定位',options)

    def _finish_close(self, p):
        import webview
        self._allow_close = True
        webview.windows[0].destroy()
        return True

    def _start_member(self, p):
        key = self._ids([p.get('id')])[0]
        members = self._ids(p.get('ids', []))
        if key not in members:
            raise ValueError('此角色已不在当前方案中，请刷新后重试')
        if self._running(self._state(key)):
            window_layout.act(self._state(key), self._app.process_stamp, focus=True)
            return {'id': key, 'focused': True}
        self._layout(p)  # Validate the full arrangement, retaining this member's slot.
        options = {**p, 'ids': [key], 'layout_ids': members, 'single': True}
        result = self._start(options)[0]
        if result.get('error'):
            raise ValueError(result['error'])
        return result

    def _single_start(self, p):
        key = self._ids([p.get('id')])[0]
        if self._running(self._state(key)):
            window_layout.act(self._state(key), self._app.process_stamp, focus=True)
            return {'id': key, 'focused': True}
        options = {'ids': [key], 'single': True, 'profiles': {},
                   'settings': {'width': 960, 'height': 540, 'columns': 1, 'gap': 0,
                                'padding': 8, 'aspect': True, 'mode': '网格排列'}}
        result = self._start(options)[0]
        if result.get('error'):
            raise ValueError(result['error'])
        return result

    def _start(self, p):
        request_id = p.get('request_id')
        if request_id is not None and (not isinstance(request_id,str) or not 1<=len(request_id)<=80):
            raise ValueError('启动请求标识无效')
        ids = self._ids(p['ids'])
        if 'layout_ids' in p:
            layout_ids = self._ids(p['layout_ids'])
            if any(key not in layout_ids for key in ids):
                raise ValueError('启动角色不在方案排列列表内')
        if not ids:
            raise ValueError('请先勾选角色')
        roles = {a['id']: a for a in self._roles()}
        self._launch_preflight({'ids': p.get('layout_ids', ids)})
        if len(ids) > 1 and any(not roles[i].get('confirmed') for i in ids):
            raise ValueError('待确认角色请一次只启动一个')
        game, exe = self._app.find_game(self._config()['game'])
        result = []
        for key in ids:
            role = roles[key]
            if role.get('imported') and role.get('cache_mode') != 'fresh-single-role':
                result.append({'id': key, 'needs_rebind': True})
                continue
            try:
                if self._running(self._state(key)):
                    window_layout.act(self._state(key), self._app.process_stamp, focus=True)
                    result.append({'id': key, 'focused': True})
                    continue
                preferences = game_preferences.resolve(self._config(), key, p.get('game_preferences'))
                self._launch_status[key] = {'phase':'starting','error':'',**({'request_id':request_id} if request_id else {})}
                if role.get('proxy_id'):
                    provider = self._config().get('proxy_backend','builtin')
                    ticket = self._laoyu_start(key, role['proxy_id'], preferences) if provider=='laoyu' else self._proxy_trial_start({'role_id': key, 'proxy_id': role['proxy_id'], 'game_preferences':preferences})
                    threading.Thread(target=self._watch_proxy_start,
                                     args=(key, ticket, copy.deepcopy(p), provider), daemon=True).start()
                    result.append({'id': key, 'proxy': True, 'starting': True})
                    continue
                child, profile = self._app.launch(game, exe, key, preferences)
                self._children.append(child)
                threading.Thread(target=self._title_later, args=(key, copy.deepcopy(p)), daemon=True).start()
                self._note(f'已启动 {role.get("name", "新角色")}，PID {child.pid}')
                result.append({'id': key, 'pid': child.pid, 'pending': not role.get('confirmed')})
            except (OSError, ValueError, RuntimeError) as error:
                self._launch_result(key,'failed',str(error),p)
                result.append({'id': key, 'error': str(error)})
        return result

    def _add(self, p):
        cfg = self._config()
        role = {'id': uuid.uuid4().hex, 'name': '新角色（等待登录）', 'confirmed': False, 'group': p.get('group') or '未分组'}
        cfg['pending'].append(role)
        self._save(cfg)
        result = self._start({'ids': [role['id']]})
        if result and result[0].get('error'):
            raise ValueError(result[0]['error'])
        return role

    def _read(self, p):
        key = self._ids([p['id']])[0]
        state = self._state(key)
        if not self._running(state):
            raise ValueError('请先启动此角色的游戏窗口')
        profile = self._app.account_folder(self._app.DATA / 'profiles', key)
        servers = self._app.read_json(ROOT / 'servers.json', {})['servers']
        identity = role_reader.read_identity(state['pid'], state['stamp'], self._app.process_stamp,
                                             profile / 'game/Documents/clientconfig', servers)
        return identity

    def _confirm(self, p):
        identity = self._read(p)
        if identity != p['identity']:
            raise ValueError('角色信息已变化，请重新核对')
        self._save(role_reader.confirm_role(self._config(), p['id'], identity))
        self._note(f'已保存角色：{identity["nickname"]} · {identity["server"]}')

    def _role_view(self, p):
        view = p.get('view')
        if view not in ('cards', 'list', 'table'):
            raise ValueError('不支持的角色视图')
        cfg = self._config()
        cfg.setdefault('ui_preferences', {})['role_view'] = view
        self._save(cfg)
        return view

    def _member_view(self, p):
        view = p.get('view')
        if view not in ('cards', 'list', 'table'):
            raise ValueError('不支持的角色视图')
        cfg = self._config()
        cfg.setdefault('ui_preferences', {})['member_view'] = view
        self._save(cfg)
        return view

    def _launch_preflight(self, p):
        ids = self._ids(p.get('ids', []))
        roles = {a['id']: a for a in self._roles()}
        for key in ids:
            profile=device_identity.normalize(roles[key].get('device_identity'))
            if profile and profile['enabled']:
                if not roles[key].get('confirmed'):
                    raise ValueError('请先以关闭设备实验的方式完成角色登录确认')
                if not (ROOT/'hardware/IdentityView.dll').is_file():
                    raise ValueError('设备实验组件缺失，已阻止启动')
        proxied = [roles[key] for key in ids if roles[key].get('proxy_id')]
        backend = self._config().get('proxy_backend','builtin')
        if backend != 'laoyu' and len(proxied) > 1:
            raise ValueError('当前同时支持 1 个 TCP 代理角色；此方案包含多个代理角色，请先调整角色绑定或分别启动')
        trial = self._proxy_trial_status()
        if backend=='laoyu' and trial.get('active') and proxied:
            raise ValueError('内置代理仍在运行，请先关闭该角色再使用老鱼')
        if backend!='laoyu' and any(x.get('active') for x in self._laoyu_states().values()) and proxied:
            raise ValueError('老鱼代理角色仍在运行，请先关闭后再使用内置代理')
        if trial.get('active') and trial.get('role_id') in ids and not self._running(self._state(trial['role_id'])):
            raise ValueError('此角色的代理正在准备，请等待管理员授权和游戏窗口出现')
        for role in proxied:
            self._require_proxy_route(role)
            if backend!='laoyu' and trial.get('active') and trial.get('role_id') != role['id']:
                raise ValueError('已有另一个代理角色运行，请先关闭该角色；直连角色仍可启动')
        return {'ok': True, 'proxied': len(proxied), 'capacity': None if backend=='laoyu' else 1}

    def _watch_proxy_start(self, key, ticket, options, provider='builtin'):
        file = (self._root / 'data/laoyu-sessions' if provider=='laoyu' else ROOT / 'proxy-engine-experiment/tickets') / (ticket + '.json')
        deadline = time.monotonic() + 140
        while time.monotonic() < deadline:
            report = self._app.read_json(file, {})
            if report.get('phase') in ('running_tcp_trial','running_laoyu'):
                self._title_later(key, options)
                return
            trial = self._laoyu_states().get(key,{}) if provider=='laoyu' else self._proxy_trial_status()
            if report.get('phase')=='cancelled':
                with self._lock:
                    self._launch_result(key,'cancelled','',options)
                return
            if report.get('phase') in ('failed', 'broker_disconnected', 'game_exited') or not trial.get('active'):
                message = report.get('message') or '代理启动未完成或已取消；请检查管理员授权、代理连接后重试，未回退直连'
                with self._lock:
                    self._launch_result(key,'failed',message,options)
                    self._note(message)
                return
            time.sleep(.4)
        with self._lock:
            self._launch_result(key,'failed','代理启动等待超时，请先关闭该角色后重试',options)

    def _laoyu_states(self):
        requests = self._app.read_json(self._root / 'data/laoyu-requests.json', {})
        result = {}
        if not isinstance(requests,dict):
            return result
        for key, request in requests.items():
            ticket = request.get('ticket','')
            if len(ticket)!=32 or any(c not in '0123456789abcdef' for c in ticket):
                continue
            report = self._app.read_json(self._root / 'data/laoyu-sessions' / (ticket+'.json'), {})
            active = self._running(request)
            if not active and report.get('phase','starting') in ('starting','syncing_proxy','binding_proxy','running_laoyu'):
                report = {**report,'phase':'failed','message':'老鱼代理控制进程已结束，请检查角色窗口及老鱼状态后重试','error_type':'ControllerExited'}
            result[key] = {**report, 'active': active, 'role_id': key,
                           'ticket': ticket, 'provider': 'laoyu', 'phase': report.get('phase','starting')}
        return result

    def _proxy_routes(self):
        trial = self._proxy_trial_status()
        result = {trial['role_id']: {**trial,'provider':'builtin'}} if trial.get('role_id') else {}
        for key, route in self._laoyu_states().items():
            if route.get('active') or not result.get(key,{}).get('active'):
                result[key] = route
        return result

    def _proxy_backend(self, p):
        backend = p.get('backend')
        if backend not in ('builtin','laoyu'):
            raise ValueError('仅支持内置 TCP 或老鱼专业版')
        if any(x.get('active') for x in self._proxy_routes().values()):
            raise ValueError('请先关闭正在启动或运行的代理角色，再切换代理执行方式')
        port = int(p.get('port',22999))
        if not 1<=port<=65535:
            raise ValueError('老鱼 API 端口无效')
        cfg = self._config()
        cfg.update(proxy_backend=backend,laoyu_port=port)
        self._save(cfg)
        return backend

    def _laoyu_probe(self, p):
        client = laoyu_support.Client(p.get('port',22999))
        rows = client.lines()
        with self._lock:
            result = self._proxies.import_laoyu(rows, client.port)
        return {'ok':True, 'lines':len(rows), 'enabled':sum(not x.get('ban') for x in rows), **result}

    def _laoyu_sync(self, p):
        with self._lock:
            cfg = self._config()
            if cfg.get('proxy_backend')!='laoyu':
                raise ValueError('请先保存老鱼专业版为代理执行方式')
            spec = self._proxies.spec(p.get('id'))
            port = cfg.get('laoyu_port',22999)
        laoyu_support.Client(port).ensure_line(spec)
        return {'ok':True}

    def _laoyu_start(self, key, proxy_id, preferences=None):
        if self._proxy_routes().get(key,{}).get('active'):
            raise ValueError('该角色的代理正在启动或运行')
        ticket = uuid.uuid4().hex
        cfg = self._config()
        child = subprocess.Popen([sys.executable,str(ROOT/'laoyu_controller.py'),
                                  '--role',key,'--proxy',proxy_id,'--ticket',ticket,
                                  '--port',str(cfg.get('laoyu_port',22999)), '--game-prefs',json.dumps(preferences if preferences is not None else game_preferences.resolve(cfg,key))],
                                 cwd=str(ROOT),creationflags=subprocess.CREATE_NO_WINDOW)
        self._children.append(child)
        file = self._root/'data/laoyu-requests.json'
        requests = self._app.read_json(file,{})
        requests[key] = {'ticket':ticket,'pid':child.pid,'stamp':self._app.process_stamp(child.pid)}
        self._app.write_json(file,requests)
        self._note('已请求老鱼专业版代理启动，将在确认 PID 线路后运行游戏。')
        return ticket

    def _proxy_trial_status(self):
        request = self._app.read_json(self._root / 'data/proxy-trial-ui.json', {})
        ticket = request.get('ticket', '')
        if not ticket or len(ticket) != 32 or any(c not in '0123456789abcdef' for c in ticket):
            return {'active': False, 'phase': 'idle'}
        status = self._app.read_json(ROOT / 'proxy-engine-experiment/tickets' / (ticket + '.json'), {})
        active = self._running(request)
        return {**status, 'active': active, 'ticket': ticket, 'role_id': request.get('role_id'), 'proxy_id': request.get('proxy_id'),
                'phase': status.get('phase', 'starting' if active else 'not_started')}

    def _proxy_trial_start(self, p):
        if self._proxy_trial_status().get('active'):
            raise ValueError('已有代理角色启动或运行中，请先关闭该角色')
        ids = self._ids([p.get('role_id')])
        role = next(a for a in self._config()['accounts'] if a['id'] == ids[0])
        if not role.get('confirmed'):
            raise ValueError('请选择已确认的角色')
        if self._running(self._state(ids[0])):
            raise ValueError('请先退出该角色现有游戏窗口')
        proxy_id = str(p.get('proxy_id') or '')
        self._proxies.spec(proxy_id)
        engine = ROOT / 'proxy-engine-experiment'
        if not all((engine / name).is_file() for name in
                   ('game_tcp_trial.py', 'bin/YysProxyCore.dll', 'bin/WinDivert.dll', 'bin/WinDivert64.sys')):
            raise ValueError('TCP 代理组件不完整')
        ticket = uuid.uuid4().hex
        child = subprocess.Popen([sys.executable, str(engine / 'game_tcp_trial.py'),
                                  '--role', ids[0], '--proxy', proxy_id, '--ticket', ticket, '--game-prefs',json.dumps(game_preferences.resolve(self._config(),ids[0],p.get('game_preferences')))],
                                 cwd=str(ROOT), creationflags=subprocess.CREATE_NO_WINDOW)
        self._children.append(child)
        self._app.write_json(self._root / 'data/proxy-trial-ui.json',
                             {'ticket': ticket, 'role_id': ids[0], 'proxy_id': proxy_id, 'pid': child.pid,
                              'stamp': self._app.process_stamp(child.pid)})
        self._note('已请求 TCP 代理启动；管理员授权及转发保护就绪后才会运行游戏。')
        return ticket

    def _proxy_delete(self, p):
        key = p.get('id')
        if not any(x['id']==key for x in self._proxies.records()):
            raise ValueError('代理已不存在，请刷新后重试')
        bound = [a for a in self._roles() if a.get('proxy_id')==key]
        if bound:
            raise ValueError(f'此代理已绑定 {len(bound)} 个角色，请先解除绑定或改用其他代理')
        # The old standalone experiment entry can use an unbound proxy.
        trial = self._proxy_trial_status()
        if trial.get('active') and trial.get('proxy_id') in (None,key):
            raise ValueError('此代理正在使用，请结束对应角色后再删除记录')
        self._proxies.remove(key)
        self._note('已移除一条本地代理记录；老鱼原线路保持不变。')
        return True

    def _laoyu_restore(self, p):
        port = int(p.get('port',self._config().get('laoyu_port',22999)))
        if not 1<=port<=65535:
            raise ValueError('老鱼 API 端口无效')
        return self._proxies.restore_laoyu(port)

    def _proxy_save(self, p):
        old = next((x for x in self._proxies.records() if x['id']==p.get('id')),None)
        if old and old.get('laoyu_managed'):
            p = {'id':old['id'],'name':p.get('name',old['name']),'host':old['host'],
                 'port':old['port'],'enabled':old.get('enabled',True)}
        return self._proxies.save(p)

    def _proxy_dns_test(self, p):
        with self._lock:
            spec = self._proxies.spec(p.get('id'))
        started = time.monotonic()
        result = proxy_dns.probe(spec)
        result.update(latency_ms=round((time.monotonic()-started)*1000),
                      process_capture_verified=False, system_dns_verified=False)
        with self._lock:
            current = self._proxies.spec(p.get('id'))
            if any(current.get(k) != spec.get(k) for k in ('host','port','credentials')):
                raise ValueError('代理配置已变化，请重新检测')
        return result

    def _proxy_test(self, p):
        with self._lock:
            spec = self._proxies.spec(p.get('id'))
        result = proxy_support.diagnose(spec)
        with self._lock:
            current = self._proxies.spec(p.get('id'))
            if all(current.get(k) == spec.get(k) for k in ('host', 'port', 'credentials')):
                self._proxies.remember(spec['id'], result)
        return result

    def _validate_proxy_binding(self, ids, proxy_id):
        if proxy_id:
            self._proxies.spec(proxy_id)
        cfg_roles = {a['id']: a for a in self._roles()}
        routes = self._proxy_routes()
        for key in ids:
            trial = routes.get(key,{})
            if cfg_roles[key].get('proxy_id', '') != proxy_id and (self._running(self._state(key)) or self._device_session_alive(key) or (trial.get('active') and trial.get('role_id') == key)):
                raise ValueError('角色仍在运行，请退出后再修改代理绑定')

    def _clear_proxy_feedback(self, key):
        # Binding edits invalidate old workers and retire only inactive request pointers.
        # Keep session reports on disk; never touch credentials or game profiles.
        self._launch_status[key] = {'phase':'cancelled', 'error':'', 'request_id':uuid.uuid4().hex}
        file = self._root / 'data/laoyu-requests.json'
        requests = self._app.read_json(file, {})
        if key in requests and not self._running(requests[key]):
            requests.pop(key)
            self._app.write_json(file, requests)
        file = self._root / 'data/proxy-trial-ui.json'
        request = self._app.read_json(file, {})
        if request.get('role_id') == key and not self._running(request):
            self._app.write_json(file, {})

    def _proxy_bind(self, p):
        ids = self._ids(p.get('ids', []))
        if not ids:
            raise ValueError('请先选择角色')
        proxy_id = str(p.get('proxy_id') or '')
        self._validate_proxy_binding(ids, proxy_id)
        cfg = self._config()
        for role in cfg['accounts'] + cfg['pending']:
            if role['id'] in ids:
                if role.get('proxy_id', '') != proxy_id:
                    self._clear_proxy_feedback(role['id'])
                role['proxy_id'] = proxy_id
        self._save(cfg)
        return len(ids)

    def _require_proxy_route(self, role):
        if not role.get('proxy_id'):
            return
        self._proxies.spec(role['proxy_id'])
        if not role.get('confirmed'):
            raise ValueError('请先使用直连完成角色登录绑定，再启用代理')
        if self._config().get('proxy_backend')=='laoyu':
            if not (ROOT/'laoyu_controller.py').is_file():
                raise ValueError('老鱼启动组件不完整，未回退直连')
            return
        engine = ROOT / 'proxy-engine-experiment'
        if not all((engine / name).is_file() for name in
                   ('game_tcp_trial.py', 'bin/YysProxyCore.dll', 'bin/WinDivert.dll', 'bin/WinDivert64.sys')):
            raise ValueError('代理组件不完整，已阻止启动，未回退直连')

    def _role_meta(self, p):
        ids = self._ids(p.get('ids', []))
        if not ids:
            raise ValueError('请先选择角色')
        proxy_id = str(p.get('proxy_id') or '')
        if 'proxy_id' in p:
            self._validate_proxy_binding(ids, proxy_id)
        note = str(p.get('note', '')).strip()
        group = str(p.get('group', '')).strip() or '未分组'
        if len(note) > 200 or len(group) > 40:
            raise ValueError('备注最多 200 字，分组名称最多 40 字')
        prefs = game_preferences.overrides(p.get('game_preferences')) if 'game_preferences' in p else None
        device = device_identity.normalize(p.get('device_identity')) if 'device_identity' in p else None
        cfg = self._config()
        for role in cfg['accounts'] + cfg['pending']:
            if role['id'] in ids and 'device_identity' in p and role.get('device_identity') != device:
                if self._running(self._state(role['id'])) or self._device_session_alive(role['id']) or self._proxy_routes().get(role['id'],{}).get('active'):
                    raise ValueError('请先退出游戏及代理会话，再修改设备实验设置')
                if device and device['enabled'] and not role.get('confirmed'):
                    raise ValueError('请先完成角色登录确认，再开启设备实验')
        for role in cfg['accounts'] + cfg['pending']:
            if role['id'] in ids:
                role.update(note=note, group=group)
                if 'device_identity' in p:
                    role['device_identity'] = device
                if prefs is not None:
                    role['game_preferences'] = prefs
                if 'proxy_id' in p:
                    if role.get('proxy_id', '') != proxy_id:
                        self._clear_proxy_feedback(role['id'])
                    role['proxy_id'] = proxy_id
        if group != '未分组' and group not in cfg.setdefault('groups', []):
            cfg['groups'].append(group)
        self._save(cfg)

    def _remove_roles(self, p):
        ids = self._ids(p.get('ids', []))
        if not ids:
            raise ValueError('请先选择要删除的角色')
        # Validate the whole selection before making any change.
        routes = self._proxy_routes()
        if any(self._running(self._state(key)) or self._device_session_alive(key) or routes.get(key,{}).get('active') for key in ids):
            raise ValueError('所选角色仍有游戏在运行，请先正常退出后再删除')
        cfg = self._config()
        archive = cfg.setdefault('removed_roles', [])
        for collection in ('accounts', 'pending'):
            for role in cfg[collection]:
                if role['id'] in ids:
                    archive.append({'role': copy.deepcopy(role), 'collection': collection,
                                    'removed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                                    'window': cfg.get('window_profiles', {}).get(role['id'])})
            cfg[collection] = [a for a in cfg[collection] if a['id'] not in ids]
        for plan in cfg.get('layout_plans', {}).values():
            plan['roles'] = [key for key in plan.get('roles', []) if key not in ids]
            plan['windows'] = {key: value for key, value in plan.get('windows', {}).items() if key not in ids}
        for field in ('window_profiles', 'last_window_positions'):
            cfg[field] = {key: value for key, value in cfg.get(field, {}).items() if key not in ids}
        self._save(cfg)
        self._note(f'已从列表删除 {len(ids)} 个角色，本地缓存保留，可从已移除列表恢复')
        return len(ids)

    def _removed_cleanup_record(self, key):
        cfg = self._config()
        records = [r for r in cfg.get('removed_roles', []) if r['role']['id'] == key]
        if len(records) != 1:
            raise ValueError('已移除记录已变化，请刷新后重试')
        if any(r['id'] == key for r in cfg['accounts'] + cfg['pending']):
            raise ValueError('角色已恢复到当前列表，不能删除')
        if self._running(self._state(key)) or self._device_session_alive(key) or self._proxy_routes().get(key, {}).get('active'):
            raise ValueError('该角色仍有游戏或代理会话在运行，请先关闭')
        return cfg, records[0]

    def _inspect_removed(self, p):
        key = p.get('id')
        self._removed_cleanup_record(key)
        base = self._app.DATA / 'profiles'
        plan = profile_cleanup.inspect(base, self._app.account_folder(base, key))
        now = time.monotonic()
        self._cleanup_plans = {token: row for token, row in self._cleanup_plans.items() if now-row['created'] < 300}
        if len(self._cleanup_plans) >= 32:
            self._cleanup_plans.pop(next(iter(self._cleanup_plans)))
        token = uuid.uuid4().hex
        self._cleanup_plans[token] = {'role_id':key, 'created':now, 'plan':plan}
        return {field:plan[field] for field in ('root','bytes','files','resource_links','hardlinked_files')} | {'token':token}

    def _delete_removed(self, p):
        if p.get('confirmed') is not True:
            raise ValueError('请先确认永久删除角色及其私有缓存')
        key = p.get('id')
        cfg, record = self._removed_cleanup_record(key)
        ticket = self._cleanup_plans.pop(p.get('cleanup_token'), None)
        if not ticket or ticket['role_id'] != key or time.monotonic()-ticket['created'] >= 300:
            raise ValueError('删除确认已失效，请重新统计缓存后确认')
        base = self._app.DATA / 'profiles'
        expected = self._app.account_folder(base, key).absolute()
        if Path(ticket['plan']['root']) != expected:
            raise ValueError('缓存路径不匹配，已停止')
        try:
            result = profile_cleanup.execute(base, ticket['plan'])
            cfg['removed_roles'] = [r for r in cfg['removed_roles'] if r is not record]
            self._save(cfg)
        except (OSError, ValueError) as error:
            raise ValueError('清理未完成，角色记录保留；缓存可能已部分清理。请关闭相关程序后重新统计：'+str(error)) from None
        self._launch_status.pop(key, None)
        self._note('已永久删除角色及其私有缓存；共享游戏资源与平安志来源保留。')
        return {'id':key, **result}

    def _restore_role(self, p):
        cfg = self._config()
        record = next((a for a in cfg.get('removed_roles', []) if a['role']['id'] == p.get('id')), None)
        if not record:
            raise ValueError('未找到已移除角色，请刷新后重试')
        role = record['role']
        active = cfg['accounts'] + cfg['pending']
        duplicate = any(a['id'] == role['id'] or
                        (role.get('short_id') and role.get('server_id') and
                         a.get('short_id') == role['short_id'] and a.get('server_id') == role['server_id']) or
                        (role.get('pinganzhi_source_id') and a.get('pinganzhi_source_id') == role['pinganzhi_source_id'] and
                         a.get('pinganzhi_source_root') == role.get('pinganzhi_source_root')) for a in active)
        if duplicate:
            raise ValueError('此角色已在当前列表中，请使用已有角色')
        cfg[record['collection']].append(role)
        if record.get('window'):
            cfg.setdefault('window_profiles', {})[role['id']] = record['window']
        cfg['removed_roles'] = [a for a in cfg['removed_roles'] if a is not record]
        self._save(cfg)
        self._note('已恢复角色：' + str(role.get('nickname') or role.get('name')))
        return role['id']

    def _scan_sync(self, p):
        root = Path(p.get('root') or self._config().get('pinganzhi_root') or pinganzhi_sync.default_root())
        sources = pinganzhi_sync.scan_accounts(root)
        self._sources = {a['meta']['id']: a for a in sources}
        return {'root': str(root), 'accounts': [{'id': a['meta']['id'], 'nickname': a['nickname'], 'server': a['server']}
                                              for a in sources]}

    def _replace_role(self, cfg, old, new):
        old_id = old['id'] if old else None
        if old:
            new['group'] = old.get('group') or '未分组'
            new['note'] = old.get('note', '')
            new['proxy_id'] = old.get('proxy_id', '')
            new['game_preferences'] = copy.deepcopy(old.get('game_preferences',{}))
            new['device_identity'] = copy.deepcopy(old.get('device_identity'))
        cfg['accounts'] = [a for a in cfg['accounts'] if a['id'] != old_id]
        cfg['pending'] = [a for a in cfg['pending'] if a['id'] != old_id]
        cfg['accounts' if new.get('confirmed') else 'pending'].append(new)
        for plan in cfg.get('layout_plans', {}).values():
            plan['roles'] = [new['id'] if key == old_id else key for key in plan.get('roles', [])]
            plan['windows'] = {new['id'] if key == old_id else key: value for key, value in plan.get('windows', {}).items()}
        cfg['window_profiles'] = {new['id'] if key == old_id else key: value for key, value in cfg.get('window_profiles', {}).items()}

    def _sync(self, p):
        cfg = self._config()
        game, exe = self._app.find_game(cfg['game'])
        servers = self._app.read_json(ROOT / 'servers.json', {})['servers']
        results = []
        for key in p['ids']:
            try:
                source = self._sources[key]
                matches = [a for a in cfg['accounts']+cfg['pending'] if a.get('pinganzhi_source_id') == key
                           and (not a.get('pinganzhi_source_root') or
                                Path(a['pinganzhi_source_root']).resolve() == source['directory'].parent.resolve())]
                if len(matches) > 1:
                    raise ValueError('存在多个相同来源的角色，请先整理重复记录')
                old = matches[0] if matches else None
                if old and self._running(self._state(old['id'])):
                    raise ValueError('目标角色仍在运行，请先退出游戏再更新')
                role, count = pinganzhi_sync.sync_account(self._app.prepare, self._app.DATA / 'profiles', game, source, servers)
                if old is None and role.get('short_id') and role.get('server_id'):
                    matches = [a for a in cfg['accounts']+cfg['pending'] if
                               a.get('short_id') == role['short_id'] and a.get('server_id') == role['server_id']]
                    if len(matches) > 1:
                        raise ValueError('角色身份对应多条记录，请先整理重复记录')
                    old = matches[0] if matches else None
                if old and self._running(self._state(old['id'])):
                    raise ValueError('目标角色仍在运行，请先退出游戏再更新')
                self._replace_role(cfg, old, role)
                cfg['pinganzhi_root'] = str(source['directory'].parent)
                self._save(cfg)
                self._note(f'已同步 {role["nickname"]} · {role["server"]}')
                results.append({'id': key, 'role': role['id']})
            except (OSError, ValueError, KeyError) as error:
                results.append({'id': key, 'error': str(error)})
        return results

    def _reset_legacy(self, p):
        import cache_import
        cfg = self._config()
        old = next(a for a in self._roles() if a['id'] == p['id'])
        if self._running(self._state(old['id'])):
            raise ValueError('请先正常退出旧游戏窗口')
        game, exe = self._app.find_game(cfg['game'])
        identity = {k: old[k] for k in ('nickname', 'server', 'server_id', 'short_id', 'server_known')}
        role = cache_import.fresh_role(self._app.prepare, self._app.DATA / 'profiles', game, identity,
                                      self._app.read_json(ROOT / 'servers.json', {})['servers'])
        self._replace_role(cfg, old, role)
        self._save(cfg)
        return role
