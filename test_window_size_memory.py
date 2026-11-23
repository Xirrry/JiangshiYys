from pathlib import Path
from types import SimpleNamespace as NS
import json,time
from close_guard import WindowSizeMemory

root=Path('test-results')/('window-size-'+str(time.time_ns()));file=root/'data/window-state.json'
def memory(limit=(2560,1440)):return WindowSizeMemory(file,(1480,980),limit,(1120,680))
def view(width,height,state='Normal',scale=1,restore=(1300,820)):
    return NS(native=NS(Width=width,Height=height,WindowState=state,_scale=scale,RestoreBounds=NS(Width=restore[0],Height=restore[1])))
m=memory();assert m.options=={'width':1480,'height':980,'maximized':False}
assert m.capture(view(1700,1000));assert memory().options=={'width':1700,'height':1000,'maximized':False}
# Native bounds are physical; persisted dimensions are logical and do not grow with DPI.
assert m.capture(view(3840,2160,'Maximized',2,(2800,1800)));assert memory().options=={'width':1400,'height':900,'maximized':True}
m=memory();m.mark_maximized();assert m.capture(view(160,40,'Minimized',1,(1400,900)));assert memory().options['maximized']
m.mark_restored();assert m.capture(view(1500,880));assert not memory().options['maximized']
assert memory((1200,720)).size==(1200,720)
file.write_text('{broken',encoding='utf-8');assert memory().size==(1480,980)
for payload in ({'width':True,'height':900,'maximized':True},{'width':-1,'height':900},{'width':90000,'height':900},[]):
    file.write_text(json.dumps(payload),encoding='utf-8');assert memory().options=={'width':1480,'height':980,'maximized':False}
blocked=root/'blocked';blocked.write_text('file',encoding='utf-8');m=WindowSizeMemory(blocked/'window-state.json',(1480,980),(2560,1440),(1120,680));assert not m.capture(view(1400,900))
print('PASS: normal size round-trip, maximized restore bounds, per-window DPI, minimized closure, screen clamp, malformed preferences and non-blocking write failure.')
