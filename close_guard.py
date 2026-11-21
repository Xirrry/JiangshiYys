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
