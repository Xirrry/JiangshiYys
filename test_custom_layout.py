from types import SimpleNamespace
import window_layout
import test_layout as fixture

profiles = {'a': {'width': 640, 'height': 360}, 'b': {'width': 320, 'height': 180},
            'c': {'width': 480, 'height': 270}, 'd': {'width': 800, 'height': 450}}
rects = window_layout.profile_rectangles(list(profiles), (-1920, 0, 1920, 1080), profiles, columns=2)
assert rects['a'][2:] != rects['b'][2:]
for i, (x,y,w,h) in enumerate(rects.values()):
    for a,b,c,d in list(rects.values())[i+1:]:
        assert x+w <= a or a+c <= x or y+h <= b or b+d <= y
custom = {'a': {'width': 640, 'height': 360, 'x': -1800, 'y': 120}}
assert window_layout.profile_rectangles(['a'], (-1920, 0, 1920, 1080), custom, mode='自定义坐标')['a'] == (-1800,120,640,360)
try:
    window_layout.profile_rectangles(['a'], (0, 0, 1920, 1080), custom, mode='自定义坐标')
    raise AssertionError('Off-screen custom coordinates accepted')
except ValueError:
    pass
print('PASS: mixed sizes never overlap, independent custom coordinates, negative-screen support, bounds refusal.')

import tkinter as tk
from tkinter import ttk
from launcher_workspace import Workspace, AccountTree
window = tk.Tk()
window.withdraw()
data = {'accounts': [{'id': 'a', 'name': '测试角色 A'}, {'id': 'b', 'name': '测试角色 B'}], 'pending': []}
def save(value):
    global data
    data = value
left, right, toolbar = ttk.Frame(window), ttk.Frame(window), ttk.Frame(window)
tree = AccountTree(left, lambda: data, columns=('name','server','state'), show='tree headings')
for a in data['accounts']:
    tree.insert('', 'end', iid=a['id'], values=(a['name'],'测试区服','未启动'))
old_screens = window_layout.screens
window_layout.screens = lambda: [{'id':'test','work':(0,0,1920,1080),'primary':True}]
try:
    ws = Workspace(window,left,right,toolbar,tree,lambda:data,save,lambda key:{},lambda pid:None,lambda msg:None)
    tree.set_checked(['a','b'])
    tree.selection_set('a')
    ws.load_editor()
    for key,value in {'width':480,'height':270,'x':100,'y':80}.items():ws.editor_vars[key].set(str(value))
    ws.save_editor()
    assert data['window_profiles']['a']['width'] == 480
    ws.plan_name.set('独立尺寸')
    ws.save_plan()
    assert data['layout_plans']['独立尺寸']['windows']['a']['width'] == 480
    ws.profiles = {}
    ws.load_plan()
    assert ws.profiles['a']['width'] == 480
    ws.preview()
    before = ws.last_rects['a']
    scale,ox,oy,work = ws.preview_transform
    px,py = ox+(before[0]+10)*scale,oy+(before[1]+10)*scale
    ws.preview_press(SimpleNamespace(x=px,y=py))
    assert ws.drag is not None and tree.selection() == ('a',)
    ws.preview_drag(SimpleNamespace(x=px+15,y=py+12))
    ws.preview_release(SimpleNamespace())
    assert ws.vars['mode'].get() == '自定义坐标'
    assert data['window_profiles']['a']['x'] != before[0]
    # A saved v7 plan has no per-window overrides and must still load.
    data['layout_plans']['旧方案'] = {'settings':{'width':640,'height':360,'columns':2,'gap':8,'padding':8,'mode':'网格排列','aspect':True},'roles':['a'],'auto':False}
    ws.plan_name.set('旧方案')
    ws.load_plan()
    assert tree.checked == {'a'}
finally:
    window_layout.screens = old_screens
    window.destroy()
print('PASS: individual editor, per-window plan roundtrip, preview selection and drag persistence, v7 plan compatibility; no real games modified.')
