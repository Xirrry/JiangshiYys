"""Launcher-owned, opt-in transparent frames; games remain top-level windows."""
import ctypes as C
from ctypes import wintypes as W
import os
import queue
import threading
import window_layout as L


def group_rows(rows, plans, order, states, only=None):
    by_pid={r['pid']:r for r in rows};used=set();groups=[]
    names=list(dict.fromkeys([*order,*plans]))
    for name in names:
        if name not in plans or (only is not None and name!=only):continue
        members=[]
        for key in plans[name].get('roles',[]):
            state=states.get(key,{})
            row=by_pid.get(state.get('pid'))
            if row and str(row['stamp'])==str(state.get('stamp')) and row['id'] not in used:
                members.append(row);used.add(row['id'])
        if members:groups.append((name,members))
    if only is None:
        rest=sorted((r for r in rows if r['id'] not in used),key=lambda r:int(r['stamp']))
        if rest:groups.append(('未归入方案的窗口',rest))
    return groups


COLORS=('#A6753B','#578376','#94718C','#6F859B')

class LayoutSpaceError(ValueError):pass


def _sizes(width,height,frame,shrink,aspect=True):
    if not aspect:
        for percent in (range(100,0,-1) if shrink else [100]):
            cw,ch=width*percent//100,height*percent//100
            if cw>=160 and ch>=90:yield cw+frame[0],ch+frame[1]
        return
    units=int(min(width/16,height/9))
    values=range(units,9,-1) if shrink else [units]
    for unit in values:
        if unit>=10:yield unit*16+frame[0],unit*9+frame[1]


def plan_blocks(groups,work,columns=3,width=960,height=540,gap=8,padding=8,new_row=True,frame=(0,0),shrink=False,aspect=True,auto_columns=False):
    x,y,w,h=work
    for ow,oh in _sizes(width,height,frame,shrink,aspect):
        if ow>w-padding*2 or oh>h-padding*2:continue
        capacity=max(1,(w-padding*2+gap)//(ow+gap))
        cols=capacity if auto_columns else min(columns,capacity)
        result={};slot=0
        for _,members in groups:
            if new_row and slot%cols:slot+=cols-slot%cols
            for member in members:
                result[member['id']]=[x+padding+(slot%cols)*(ow+gap),y+padding+(slot//cols)*(oh+gap),ow,oh];slot+=1
        if all(r[1]+r[3]<=y+h-padding for r in result.values()):return result
    raise LayoutSpaceError('当前屏幕空间不足；请缩小窗口、减少窗口数或切换目标屏幕，不会覆盖已有窗口。')


def overlaps(a,b,gap=0):
    return a[0]<b[0]+b[2]+gap and b[0]<a[0]+a[2]+gap and a[1]<b[1]+b[3]+gap and b[1]<a[1]+a[3]+gap



class GroupFrames:
    def __init__(self, stamp_fn):
        self.stamp_fn=stamp_fn;self.commands=queue.Queue();self.ready=threading.Event()
        self.visible=False;self.error='';self.count=0;self.stopped=False
        self.thread=threading.Thread(target=self._run,name='window-group-frames',daemon=True)
        self.thread.start()
        if not self.ready.wait(5):raise RuntimeError('分组框初始化超时')
        if self.error:raise RuntimeError(self.error)

    def status(self):return {'visible':self.visible,'groups':self.count,'error':self.error}

    def command(self, action, groups=None):
        if self.stopped:raise RuntimeError('分组框已关闭')
        done=threading.Event();self.commands.put((action,groups,done))
        if not done.wait(5):raise RuntimeError('分组框响应超时')
        if self.error:raise RuntimeError(self.error)
        return self.status()

    def close(self):
        if self.stopped:return
        self.command('close');self.thread.join(2)

    def _run(self):
        root=None;frames=[];drag={}
        try:
            import tkinter as tk
            from tkinter import font as tkfont
            u=L.api()
            u.GetForegroundWindow.restype=W.HWND
            u.GetAncestor.argtypes=[W.HWND,W.UINT];u.GetAncestor.restype=W.HWND
            u.IsIconic.argtypes=[W.HWND];u.IsIconic.restype=W.BOOL
            u.SetThreadDpiAwarenessContext.argtypes=[W.HANDLE];u.SetThreadDpiAwarenessContext.restype=W.HANDLE
            previous=u.SetThreadDpiAwarenessContext(W.HANDLE(-4))
            root=tk.Tk();root.withdraw();key='#ff00ff'
            def state(row):return {'pid':row['pid'],'stamp':int(row['stamp'])}
            def bounds(row):
                hwnd=L.guarded_window(state(row),self.stamp_fn)
                if u.IsIconic(hwnd):return None
                _,r=L.visible_bounds(hwnd)
                return [r.left,r.top,r.right-r.left,r.bottom-r.top]
            def hide():
                self.visible=False;drag.clear()
                for win,_,_,_ in frames:win.withdraw()
            def start(e,rows):
                drag.clear();drag.update(x=e.x_root,y=e.y_root,rows=[(r,bounds(r)) for r in rows])
            def move(e):
                if not drag:return
                dx=e.x_root-drag['x'];dy=e.y_root-drag['y']
                if not drag.get('moved') and max(abs(dx),abs(dy))<6:return
                drag['moved']=True
                for row,r in drag['rows']:
                    if r:
                        try:L.act(state(row),self.stamp_fn,rectangle=[r[0]+dx,r[1]+dy,r[2],r[3]])
                        except (OSError,ValueError):pass
                update()
            def rebuild(groups):
                for win,_,_,_ in frames:win.destroy()
                frames.clear();drag.clear()
                for i,(name,rows) in enumerate(groups):
                    color=['#A6753B','#578376','#94718C','#6F859B'][i%4]
                    win=tk.Toplevel(root);win.withdraw();win.overrideredirect(True)
                    win.attributes('-topmost',True);win.configure(bg=key);win.wm_attributes('-transparentcolor',key)
                    canvas=tk.Canvas(win,bg=key,highlightthickness=0);canvas.pack(fill='both',expand=True)
                    # Keep the interior and most of the perimeter click-through.
                    line=tuple(canvas.create_line(0,0,1,1,fill=color,width=1) for _ in range(4))
                    paper='#F5EFE4';ink='#554638'
                    tools=tk.Frame(win,bg=paper,highlightbackground='#D8C9B5',highlightthickness=1)
                    tools.place(x=1,y=0,height=23)
                    grip=tk.Label(tools,text='⠿',font=('Segoe UI',10),bg=paper,fg=color,cursor='fleur')
                    grip.pack(side='left',padx=(5,1))
                    face=tkfont.Font(root=root,family='Microsoft YaHei UI',size=9)
                    title=name
                    while face.measure(title)>210 and len(title)>1:title=title[:-1]
                    if title!=name:title=title.rstrip()+'…'
                    label=tk.Label(tools,text=f'{title}  ·  {len(rows)}',font=face,bg=paper,fg=ink,anchor='w',cursor='fleur',pady=0)
                    label._group_font=face
                    label.pack(side='left',padx=(2,8))
                    grip.bind('<ButtonPress-1>',lambda e,rs=rows:start(e,rs));grip.bind('<B1-Motion>',move)
                    grip.bind('<ButtonRelease-1>',lambda e:drag.clear())
                    label.bind('<ButtonPress-1>',lambda e,rs=rows:start(e,rs));label.bind('<B1-Motion>',move)
                    label.bind('<ButtonRelease-1>',lambda e:drag.clear())
                    close=tk.Label(tools,text='收起',font=('Microsoft YaHei UI',9),bg=paper,fg='#8A7864',cursor='hand2',padx=7,pady=0)
                    close.pack(side='left')
                    close.bind('<Button-1>',lambda e:hide())
                    close.bind('<Enter>',lambda e:e.widget.configure(bg='#E9DECE',fg=ink))
                    close.bind('<Leave>',lambda e:e.widget.configure(bg=paper,fg='#8A7864'))
                    win.bind('<Escape>',lambda e:hide())
                    frames.append((win,canvas,line,rows))
                self.count=len(frames);self.visible=bool(frames)
            def update():
                if not self.visible:return
                pid=W.DWORD();u.GetWindowThreadProcessId(u.GetForegroundWindow(),C.byref(pid))
                allowed={os.getpid(),*[r['pid'] for _,_,_,rows in frames for r in rows]}
                if pid.value not in allowed:hide();return
                active=0
                for win,canvas,line,rows in frames:
                    rs=[]
                    for row in rows:
                        try:
                            r=bounds(row)
                            if r:rs.append(r)
                        except (OSError,ValueError):pass
                    if not rs:win.withdraw();continue
                    active+=1
                    x=min(r[0] for r in rs)-3;y=min(r[1] for r in rs)-26
                    right=max(r[0]+r[2] for r in rs)+3;bottom=max(r[1]+r[3] for r in rs)+3
                    # Use the matching monitor, including negative-coordinate desktops.
                    screen=next((s['work'] for s in L.screens() if s['work'][0]<=x+3<s['work'][0]+s['work'][2] and s['work'][1]<=y+26<s['work'][1]+s['work'][3]),None)
                    if screen:y=max(screen[1],y)
                    w=right-x;h=bottom-y
                    win.geometry(f'{w}x{h}')
                    top=max(24,min(r[1] for r in rs)-y-2);corner=12
                    segments=[(1,top+corner,1,top,1+corner,top),
                              (w-1-corner,top,w-1,top,w-1,top+corner),
                              (1,h-1-corner,1,h-1,1+corner,h-1),
                              (w-1-corner,h-1,w-1,h-1,w-1,h-1-corner)]
                    for item,points in zip(line,segments):canvas.coords(item,*points)
                    win.deiconify();win.update_idletasks()
                    u.SetWindowPos(u.GetAncestor(win.winfo_id(),2),W.HWND(-1),x,y,w,h,0x0010)
                if not active:hide()
            def tick():
                while not self.commands.empty():
                    action,groups,done=self.commands.get_nowait()
                    try:
                        self.error=''
                        if action=='show':rebuild(groups);update()
                        elif action=='hide':hide()
                        elif action=='close':hide();root.quit();self.stopped=True
                    except Exception as error:self.error=str(error);hide()
                    finally:done.set()
                try:update()
                except Exception as error:self.error=str(error);hide()
                if not self.stopped:root.after(100,tick)
            self.ready.set();root.after(20,tick);root.mainloop()
        except Exception as error:self.error=str(error);self.ready.set()
        finally:
            self.visible=False;self.stopped=True
            if root is not None:root.destroy()
            frames.clear();drag.clear();root=None
            # Dispose Tcl references on their owning thread before Python shutdown.
            import gc
            gc.collect()
            if 'previous' in locals():u.SetThreadDpiAwarenessContext(previous)
