"""Vue 3 / WebView2 desktop shell. Existing Python launcher remains the backend."""
from pathlib import Path
import sys
import traceback
import json

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
BRAND = json.loads((ROOT / 'brand.json').read_text(encoding='utf-8'))


def main():
    import msvcrt
    def stage(name):
        (ROOT / 'desktop-stage.txt').write_text(name, encoding='utf-8')
    stage('initializing')
    import ctypes
    # Opt into per-monitor rendering before CLR creates any native controls.
    # This affects this launcher process only, never the game's display settings.
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('XiNai.JiangshiYys.Launcher')
    stage('import-webview')
    import webview
    stage('webview-imported')
    from desktop_api import DesktopApi
    (ROOT / 'data').mkdir(exist_ok=True)
    lock = (ROOT / 'data/launcher.lock').open('a+b')
    try:
        if (ROOT / 'data/launcher.lock').stat().st_size == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        ctypes.windll.user32.MessageBoxW(None, '启动器已打开，请先关闭旧窗口再启动新版。', '角色启动器', 0)
        return
    entry = ROOT / 'frontend/dist/index.html'
    if not entry.is_file():
        raise RuntimeError('缺少前端构建文件 frontend/dist/index.html')
    stage('bridge')
    api = DesktopApi()
    stage('create-window')
    width, height = 1480, 980
    try:
        primary = __import__('window_layout').screens()[0]
        scale = ctypes.windll.user32.GetDpiForSystem() / 96
        width = min(width, max(800, int(primary['work'][2] / scale) - 24))
        height = min(height, max(540, int(primary['work'][3] / scale) - 24))
    except (AttributeError, OSError, IndexError):
        pass
    view = webview.create_window(BRAND['name'] + ' · v' + BRAND['version'], str(entry), js_api=api,
                          width=width, height=height, min_size=(min(1120,width), min(680,height)), background_color='#f6f2ea',
                          text_select=False)
    from close_guard import CloseGuard
    import threading
    def defer_close(callback):
        def run():
            import time
            time.sleep(0.05)  # Let FormClosing return before requesting browser UI.
            callback()
        threading.Thread(target=run, daemon=True).start()
    def request_close():
        try:
            handled = view.evaluate_js("Boolean(window.__requestLauncherClose && window.__requestLauncherClose())")
            if handled:
                return
        except Exception:
            pass
        if view.create_confirmation_dialog('关闭启动器', '界面尚未就绪，确认关闭启动器？'):
            api._allow_close = True
            view.destroy()
    view.events.closing += CloseGuard(lambda: api._allow_close, defer_close, request_close)
    def on_start():
        import time, json
        stage('gui-started')
        view.show()
        for attempt in range(15):
            time.sleep(1)
            try:
                health = view.evaluate_js("({connected:!document.querySelector('.connecting'),layout:!!document.querySelector('.layout-card'),groups:document.querySelectorAll('.account-group').length,width:document.documentElement.clientWidth,dpr:window.devicePixelRatio,font:getComputedStyle(document.body).fontFamily,viewportHeight:innerHeight,pageHeight:document.documentElement.scrollHeight,layoutBottom:document.querySelector('.layout-card')?.getBoundingClientRect().bottom,controlsBottom:document.querySelector('.layout-footer')?.getBoundingClientRect().bottom,horizontalOverflow:document.documentElement.scrollWidth>innerWidth})")
                (ROOT / 'desktop-health.json').write_text(json.dumps(health), encoding='utf-8')
                if health.get('connected') and health.get('layout'):
                    break
            except Exception:
                pass
    view.events.loaded += lambda: stage('page-loaded')
    stage('starting-gui')
    webview.start(on_start, gui='edgechromium', http_server=True, debug=False, private_mode=True, icon=str(ROOT / 'assets/app-icon.ico'))
    lock.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        (ROOT / 'desktop-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, '界面未能打开，详情见 desktop-error.log。旧版仍可运行 launcher.pyw。', '启动失败', 0)
