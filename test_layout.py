import copy
import tkinter as tk
from tkinter import ttk
import window_layout
from launcher_workspace import AccountTree, Workspace, theme

for count in (1, 2, 8, 29):
    for work in [(0, 0, 1920, 1040), (-1920, -100, 1920, 1080)]:
        result = window_layout.rectangles(list(range(count)), work, columns=6 if count == 29 else 3, frame=(16, 39))
        assert len(result) == count
        rectangles = list(result.values())
        for x, y, w, h in rectangles:
            assert x >= work[0] and y >= work[1]
            assert x+w <= work[0]+work[2] and y+h <= work[1]+work[3]
            assert (w-16)*9 == (h-39)*16
        for i, (x, y, w, h) in enumerate(rectangles):
            for a, b, c, d in rectangles[i+1:]:
                assert x+w <= a or a+c <= x or y+h <= b or b+d <= y
assert window_layout.rectangles([], (0, 0, 100, 100)) == {}
for bad in [{'columns': 0}, {'gap': -1}, {'padding': 600}, {'width': 10}]:
    try:
        window_layout.rectangles(['a'], (0, 0, 1920, 1080), **bad)
        raise AssertionError('Invalid geometry accepted')
    except ValueError:
        pass
try:
    window_layout.guarded_window({'pid': 123, 'stamp': 1}, lambda pid: 2)
    raise AssertionError('Reused PID accepted')
except ValueError:
    pass
print('PASS: screen bounds, negative screen origins, no grid overlaps, exact 16:9, invalid inputs, reused-PID guard.')

# Isolated UI fixture: no real game operations and no production configuration writes.
window = tk.Tk()
window.withdraw()
theme(window)
data = {'accounts': [{'id': 'one', 'name': '角色一', 'group': '第一组'}, {'id': 'two', 'name': '角色二'}], 'pending': [], 'groups': ['第一组']}
def save(value):
    global data
    data = copy.deepcopy(value)
left, right, toolbar = ttk.Frame(window), ttk.Frame(window), ttk.Frame(window)
tree = AccountTree(left, lambda: data, columns=('name', 'server', 'state'), show='tree headings')
for a in data['accounts']:
    tree.insert('', 'end', iid=a['id'], values=(a['name'], '测试区服', '未启动'))
tree.set_checked(['one'])
assert tree.launch_ids() == ('one',)
tree.selection_set(tree.group_parent('第一组'))
assert tree.selection() == ()
old_screens = window_layout.screens
window_layout.screens = lambda: [{'id': 'test', 'work': (0, 0, 1920, 1040), 'primary': True}]
try:
    workspace = Workspace(window, left, right, toolbar, tree, lambda: data, save, lambda key: {}, lambda pid: None, lambda text: None)
    tree.set_checked(['one', 'two'])
    workspace.plan_name.set('八开方案')
    workspace.save_plan()
    assert data['layout_plans']['八开方案']['roles'] == ['one', 'two']
    tree.set_checked([])
    workspace.vars['width'].set('800')
    workspace.load_plan()
    assert tree.checked == {'one', 'two'} and workspace.vars['width'].get() == '640'
    tree.selection_set('two')
    workspace.group.set('第一组')
    workspace.assign_group()
    assert tree.parent('one') == tree.parent('two')
    assert next(a for a in data['accounts'] if a['id'] == 'two')['group'] == '第一组'
    tree.delete('one')
    assert 'one' not in tree.checked
    window.update_idletasks()
    import os
    window.title('YYS isolated window test')
    window.geometry('420x260+20+20')
    window.deiconify()
    window.update()
    state = {'pid': os.getpid(), 'stamp': 42}
    actual = window_layout.act(state, lambda pid: 42, rectangle=(50, 50, 640, 400), title='YYS test renamed')
    assert actual == (50, 50, 640, 400), actual
    window_layout.act(state, lambda pid: 42, close=True)
    window.update()
    print('PASS: native x64 window discovery, title, exact outer rectangle and normal close on test window only.')
finally:
    window_layout.screens = old_screens
    try:
        window.destroy()
    except tk.TclError:
        pass
print('PASS: grouped role tree, checked-only targets, group headers excluded, group assignment, plan save/load, deleted-role checkbox cleanup.')
