"""Defer close decisions so the native UI thread stays free for the web dialog."""
class CloseGuard:
    def __init__(self, allowed, schedule, request):
        self.allowed, self.schedule, self.request = allowed, schedule, request
        self.pending = False

    def __call__(self):
        if self.allowed():
            return True
        if not self.pending:
            self.pending = True
            self.schedule(self._request)
        return False

    def _request(self):
        try:
            self.request()
        finally:
            self.pending = False


class WindowSizeMemory:
    """Persist launcher geometry in logical pixels, separate from account data."""
    def __init__(self, file, default, limit, minimum):
        import json
        from pathlib import Path
        self.file=Path(file);self.limit=limit;self.minimum=minimum
        self.size=tuple(default);self.maximized=False
        try:
            data=json.loads(self.file.read_text(encoding='utf-8'))
            values=(data.get('width'),data.get('height'))
            if all(type(value) is int and 160<=value<=32768 for value in values):
                self.size=self._clamp(values)
                self.maximized=data.get('maximized') is True
        except (OSError,ValueError,TypeError,AttributeError):pass

    def _clamp(self, size):
        return tuple(max(minimum,min(limit,value)) for value,limit,minimum in zip(size,self.limit,self.minimum))

    @property
    def options(self):
        return {'width':self.size[0],'height':self.size[1],'maximized':self.maximized}

    def mark_maximized(self):self.maximized=True
    def mark_restored(self):self.maximized=False

    def capture(self, view):
        import json
        try:
            native=getattr(view,'native',None)
            if native is not None:
                state=str(native.WindowState)
                scale=float(native._scale)
                if not 0.25<=scale<=8:scale=1.0
                if state=='Normal':
                    values=(round(native.Width/scale),round(native.Height/scale));self.maximized=False
                else:
                    bounds=native.RestoreBounds
                    values=(round(bounds.Width/scale),round(bounds.Height/scale))
                    if state=='Maximized':self.maximized=True
            else:values=(int(view.width),int(view.height))
            if all(160<=value<=32768 for value in values):self.size=self._clamp(values)
            self.file.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.file.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(self.options,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            temporary.replace(self.file)
            return True
        except Exception:
            # Closing must remain possible if a preference cannot be written.
            return False


class UniformUiScale:
    """Stable per-screen zoom; window resizing never changes zoom or density."""
    MIN_AUTO = 0.8

    def __init__(self, reference_width=1600, preferences_file=None):
        import json
        from pathlib import Path
        self.reference_width=float(reference_width)
        if not 1200<=self.reference_width<=3840:raise ValueError('Invalid reference width')
        self.file=Path(preferences_file) if preferences_file is not None else None
        self.preferences={'mode':'auto','percent':100}
        if self.file:
            try:self.preferences=self._normalize(json.loads(self.file.read_text(encoding='utf-8')))
            except (OSError,ValueError,TypeError):pass
        self.factor=1.0;self.error='';self._native=None;self._browser=None
        self._resize_handler=None;self._dpi_handler=None;self._move_handler=None
        self._screen={};self._dpi=1.0;self._density='comfortable';self._limited=False
        self._last_public=''

    @staticmethod
    def _normalize(value):
        if not isinstance(value,dict) or value.get('mode') not in ('auto','manual'):raise ValueError('请选择自动或手动缩放')
        percent=value.get('percent',100)
        if type(percent) is not int or not 80<=percent<=150:raise ValueError('缩放比例需在 80% 到 150% 之间')
        return {'mode':value['mode'],'percent':percent}

    @staticmethod
    def _dpi_value(value):
        import math
        dpi=float(value)
        return dpi if math.isfinite(dpi) and 0.25<=dpi<=8 else 1.0

    def recommendation(self, screen_work, dpi_scale=1):
        import math
        dpi=self._dpi_value(dpi_scale)
        width,height=(float(value)/dpi for value in screen_work)
        if not all(math.isfinite(value) and value>0 for value in (width,height)):return 1.0
        # Initial calibrated range: retain the current 2K/4K density, gently reduce
        # 1080p/limited logical desktops instead of a literal 50% pixel-ratio zoom.
        return min(max(.85,min(1.0,width/2560)),max(.85,min(1.0,height/1080)))

    def zoom_for(self, physical_width, dpi_scale=1, screen_work=(3840,2160)):
        import math
        width=float(physical_width);dpi=self._dpi_value(dpi_scale)
        if not math.isfinite(width) or width<160:return None
        if self.preferences['mode']=='manual':return self.preferences['percent']/100
        return self.recommendation(screen_work,dpi)

    def configure(self, value):
        import json
        preferences=self._normalize(value)
        if self.file:
            self.file.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.file.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(preferences,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            temporary.replace(self.file)
        self.preferences=preferences
        if self._native is not None:
            from System import Action
            if self._native.InvokeRequired:self._native.Invoke(Action(self._apply))
            else:self._apply()
        return self.status

    def attach(self, view):
        try:
            from System import Action
            native=view.native
            def install():
                if self._native is native and self._browser is not None:
                    self._last_public='';self._apply();return
                self._native=native;self._browser=native.webview
                self._browser.CoreWebView2.Settings.IsZoomControlEnabled=False
                self._resize_handler=lambda sender,args:self._apply()
                self._browser.SizeChanged+=self._resize_handler
                self._dpi_handler=lambda sender,args:self._apply()
                self._browser.DpiChangedAfterParent+=self._dpi_handler
                self._move_handler=lambda sender,args:self._apply()
                native.LocationChanged+=self._move_handler
                self._apply()
            if native.InvokeRequired:native.Invoke(Action(install))
            else:install()
            return not self.error
        except Exception as error:
            self.error=str(error);return False

    def _apply(self):
        try:
            import json
            from System.Windows.Forms import Screen
            if self._browser.IsDisposed or str(self._native.WindowState)=='Minimized':return
            screen=Screen.FromControl(self._native);work=screen.WorkingArea;bounds=screen.Bounds
            dpi=self._dpi_value(self._native._scale);width=self._browser.ClientSize.Width
            preferred=self.recommendation((work.Width,work.Height),dpi)
            factor=self.zoom_for(width,dpi,(work.Width,work.Height))
            if factor is None:return
            if abs(float(self._browser.ZoomFactor)-factor)>0.00001:self._browser.ZoomFactor=factor
            self.factor=factor;self._dpi=dpi
            self._screen={'width':int(bounds.Width),'height':int(bounds.Height),'logical_width':round(work.Width/dpi),'logical_height':round(work.Height/dpi)}
            self._density='compact' if preferred<1 else 'comfortable'
            self._limited=width/dpi/factor<1200
            self.error=''
            # Publish only when displayed settings change, not on every dragged pixel.
            public=self.status;public['factor']=round(public['factor'],2)
            value=json.dumps(public,ensure_ascii=True,sort_keys=True)
            if value!=self._last_public:
                self._last_public=value
                code="document.documentElement.dataset.uiAdapted='true';document.documentElement.dataset.uiDensity="+json.dumps(self._density)+";window.dispatchEvent(new CustomEvent('launcher-ui-scale',{detail:"+value+"}));"
                self._browser.CoreWebView2.ExecuteScriptAsync(code)
        except Exception as error:
            self.error=str(error)

    @property
    def status(self):
        return {**self.preferences,'factor':self.factor,'density':self._density,'screen':dict(self._screen),'dpi':self._dpi,'minimum':self.MIN_AUTO,'limited':self._limited,'active':self._browser is not None,'error':self.error}
