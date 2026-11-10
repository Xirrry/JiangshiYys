import hashlib
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import window_layout

BG, CARD, INK, MUTED, ACCENT = '#f5f0e7', '#fffdf8', '#352d26', '#827366', '#a94030'


def theme(window):
    window.configure(bg=BG)
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('.', font=('Microsoft YaHei UI', 10), background=BG, foreground=INK)
    style.configure('TFrame', background=BG)
    style.configure('Card.TFrame', background=CARD)
    style.configure('TLabel', background=BG)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('TButton', padding=(10, 7), background='#eee5d8', borderwidth=1)
    style.map('TButton', background=[('active', '#e6d8c7')])
    style.configure('Accent.TButton', background=ACCENT, foreground='white')
    style.map('Accent.TButton', background=[('active', '#8d3527')])
    style.configure('Treeview', background=CARD, fieldbackground=CARD, rowheight=34, borderwidth=0)
    style.configure('Treeview.Heading', background='#eee6d9', padding=(8, 8))
    style.map('Treeview', background=[('selected', '#ead8c5')], foreground=[('selected', INK)])
    style.configure('TLabelframe', background=BG, bordercolor='#e5dac9', padding=12)
    style.configure('TLabelframe.Label', font=('Microsoft YaHei UI', 11, 'bold'), foreground=INK)


class AccountTree(ttk.Treeview):
    def __init__(self, parent, config, **kwargs):
        super().__init__(parent, **kwargs)
        self.config_data = config
        self.checked = set()
        self.groups = {}
        self.heading('#0', text='勾选 / 分组')
        self.column('#0', width=135, minwidth=100, stretch=False)
        self.bind('<Button-1>', self.toggle_click)
        self.bind('<space>', self.toggle_selection)

    def all_roles(self):
        data = self.config_data()
        return data['accounts'] + data.get('pending', [])

    def group_parent(self, group):
        key = 'group:' + hashlib.sha256(group.encode()).hexdigest()[:16]
        if not self.exists(key):
            super().insert('', 'end', iid=key, text='☐ ' + group, open=True)
        self.groups[key] = group
        return key

    def insert(self, parent, index, iid=None, **kwargs):
        if iid and not iid.startswith('group:'):
            role = next((a for a in self.all_roles() if a['id'] == iid), {})
            parent = self.group_parent(role.get('group') or '未分组')
            kwargs['text'] = '☑' if iid in self.checked else '☐'
        result = super().insert(parent, index, iid=iid, **kwargs)
        self.update_groups()
        return result

    def selection(self):
        return tuple(i for i in super().selection() if not i.startswith('group:'))

    def delete(self, *items):
        self.checked.difference_update(items)
        super().delete(*items)
        self.update_groups()

    def launch_ids(self):
        return tuple(a['id'] for a in self.all_roles() if a['id'] in self.checked and self.exists(a['id'])) or self.selection()

    def update_groups(self):
        for key, name in list(self.groups.items()):
            if not self.exists(key):
                continue
            ids = self.get_children(key)
            mark = '☑' if ids and all(i in self.checked for i in ids) else '☐'
            self.item(key, text=f'{mark} {name} ({len(ids)})')

    def regroup(self):
        for role in self.all_roles():
            if self.exists(role['id']):
                self.move(role['id'], self.group_parent(role.get('group') or '未分组'), 'end')
        for name in self.config_data().get('groups', []):
            self.group_parent(name)
        self.update_groups()

    def set_checked(self, ids):
        self.checked = {i for i in ids if self.exists(i) and not i.startswith('group:')}
        for role in self.all_roles():
            if self.exists(role['id']):
                self.item(role['id'], text='☑' if role['id'] in self.checked else '☐')
        self.update_groups()
        self.event_generate('<<ChecksChanged>>')

    def toggle_click(self, event):
        row = self.identify_row(event.y)
        if self.identify_column(event.x) != '#0' or not row or 'indicator' in self.identify_element(event.x, event.y):
            return
        ids = self.get_children(row) if row.startswith('group:') else [row]
        checked = set(self.checked)
        if ids and all(i in checked for i in ids):
            checked.difference_update(ids)
        else:
            checked.update(ids)
        self.set_checked(checked)
        return 'break'

    def toggle_selection(self, event):
        ids = self.selection()
        checked = set(self.checked)
        for key in ids:
            if key in checked:
                checked.remove(key)
            else:
                checked.add(key)
        self.set_checked(checked)
        return 'break'


class Workspace:
    def __init__(self, window, left, right, toolbar, tree, get_config, save, state, stamp, note):
        self.window, self.tree, self.config, self.save = window, tree, get_config, save
        self.state, self.stamp, self.note = state, stamp, note
        self.positions = dict(self.config().get('last_window_positions', {}))
        self.titled = set()
        self.was_running = set()
        self.profiles = {k: dict(v) for k, v in self.config().get('window_profiles', {}).items()}
        self.editor_vars = {k: tk.StringVar() for k in ('width', 'height', 'x', 'y')}
        self.editor_name = tk.StringVar(value='选中一个角色编辑独立窗口')
        self.drag = None
        self.last_rects = {}
        self.last_frame = (0, 0)
        self.monitors = []
        self.vars = {k: tk.StringVar(value=v) for k, v in {
            'width': '640', 'height': '360', 'columns': '3', 'gap': '8', 'padding': '8', 'mode': '网格排列'}.items()}
        self.aspect = tk.BooleanVar(value=True)
        self.auto = tk.BooleanVar(value=False)
        self.plan_name = tk.StringVar(value='默认方案')
        self.monitor = tk.StringVar()
        self.count = tk.StringVar()
        self.group = tk.StringVar(value='未分组')
        heading = ttk.Frame(left)
        heading.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(heading, text='角色与分组', font=('Microsoft YaHei UI', 13, 'bold')).pack(side='left')
        ttk.Label(heading, textvariable=self.count, style='Muted.TLabel').pack(side='right')
        tools = ttk.Frame(left)
        tools.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        self.group_combo = ttk.Combobox(tools, textvariable=self.group, width=12, state='readonly')
        self.group_combo.pack(side='left')
        for label, command in [('新分组', self.new_group), ('移入分组', self.assign_group), ('重命名', self.rename_group), ('取消分组', self.remove_group)]:
            ttk.Button(tools, text=label, command=command).pack(side='left', padx=(5, 0))
        checks = ttk.Frame(left)
        checks.grid(row=3, column=0, sticky='ew', pady=(8, 0))
        ttk.Button(checks, text='全选', command=lambda: tree.set_checked([a['id'] for a in tree.all_roles()])).pack(side='left')
        ttk.Button(checks, text='清空勾选', command=lambda: tree.set_checked([])).pack(side='left', padx=6)
        ttk.Label(checks, text='点击左侧方框勾选；启动时优先使用勾选项', style='Muted.TLabel').pack(side='left')
        ttk.Button(toolbar, text='关闭全部已跟踪窗口', command=self.close_all).pack(side='right', padx=6)
        ttk.Button(toolbar, text='关闭所选', command=self.close_selected).pack(side='right')
        self.build_panel(right)
        tree.bind('<<ChecksChanged>>', lambda e: self.preview(), add=True)
        tree.bind('<<TreeviewSelect>>', lambda e: (self.preview(), self.load_editor()), add=True)
        self.refresh_groups()
        self.refresh_screens()
        for var in self.vars.values():
            var.trace_add('write', lambda *args: self.preview())
        self.aspect.trace_add('write', lambda *args: self.preview())
        self.monitor.trace_add('write', lambda *args: self.preview())
        plans = self.config().get('layout_plans', {})
        if plans:
            self.plan_name.set(next(iter(plans)))
            self.load_plan()
        self.tick()

    def build_panel(self, parent):
        footer = ttk.Frame(parent)
        footer.pack(side='bottom', fill='x', pady=(10, 0))
        ttk.Button(footer, text='排列所选窗口', command=self.arrange, style='Accent.TButton').pack(fill='x', pady=(0, 5))
        ttk.Button(footer, text='恢复上次排列位置', command=self.restore).pack(fill='x')
        scroll = ttk.Frame(parent)
        scroll.pack(fill='both', expand=True)
        scroll.columnconfigure(0, weight=1)
        scroll.rowconfigure(0, weight=1)
        viewport = tk.Canvas(scroll, width=355, height=400, bg=BG, highlightthickness=0)
        viewport.grid(row=0, column=0, sticky='nsew')
        bar = ttk.Scrollbar(scroll, orient='vertical', command=viewport.yview)
        bar.grid(row=0, column=1, sticky='ns')
        viewport.configure(yscrollcommand=bar.set)
        card = ttk.LabelFrame(viewport, text='排列方案', padding=14)
        item = viewport.create_window(0, 0, anchor='nw', window=card)
        card.bind('<Configure>', lambda e: viewport.configure(scrollregion=viewport.bbox('all')))
        viewport.bind('<Configure>', lambda e: viewport.itemconfigure(item, width=e.width))
        viewport.bind('<MouseWheel>', lambda e: viewport.yview_scroll(-int(e.delta/120), 'units'))
        self.plan_combo = ttk.Combobox(card, textvariable=self.plan_name, values=list(self.config().get('layout_plans', {})))
        self.plan_combo.pack(fill='x')
        self.plan_combo.bind('<<ComboboxSelected>>', lambda e: self.load_plan())
        actions = ttk.Frame(card)
        actions.pack(fill='x', pady=8)
        for label, command in [('保存', self.save_plan), ('载入', self.load_plan), ('删除方案', self.remove_plan)]:
            ttk.Button(actions, text=label, command=command).pack(side='left', padx=(0, 5))
        ttk.Label(card, text='目标屏幕', style='Muted.TLabel').pack(anchor='w', pady=(6, 4))
        self.screen_combo = ttk.Combobox(card, textvariable=self.monitor, state='readonly')
        self.screen_combo.pack(fill='x')
        ttk.Button(card, text='刷新屏幕', command=self.refresh_screens).pack(anchor='e', pady=5)
        self.canvas = tk.Canvas(card, height=185, bg='#242c35', highlightthickness=0)
        self.canvas.pack(fill='x', pady=(4, 10))
        self.canvas.bind('<Configure>', lambda e: self.preview())
        self.canvas.bind('<ButtonPress-1>', self.preview_press)
        self.canvas.bind('<B1-Motion>', self.preview_drag)
        self.canvas.bind('<ButtonRelease-1>', self.preview_release)
        ttk.Combobox(card, textvariable=self.vars['mode'], values=['网格排列', '错落排列', '自定义坐标'], state='readonly').pack(fill='x')
        fields = ttk.Frame(card)
        fields.pack(fill='x', pady=10)
        for i, (key, label) in enumerate([('width', '画面宽度'), ('height', '画面高度'), ('columns', '列数'), ('gap', '窗口间距'), ('padding', '四周留白')]):
            row, col = divmod(i, 2)
            cell = ttk.Frame(fields)
            cell.grid(row=row, column=col, sticky='ew', padx=(0, 8), pady=4)
            fields.columnconfigure(col, weight=1)
            ttk.Label(cell, text=label, style='Muted.TLabel').pack(anchor='w')
            ttk.Entry(cell, textvariable=self.vars[key], width=13).pack(fill='x', pady=(3, 0))
        ttk.Checkbutton(card, text='固定游戏画面比例 16:9', variable=self.aspect).pack(anchor='w', pady=3)
        ttk.Checkbutton(card, text='启动后自动排列', variable=self.auto).pack(anchor='w', pady=3)
        editor = ttk.LabelFrame(card, text='所选角色的窗口', padding=10)
        editor.pack(fill='x', pady=10)
        ttk.Label(editor, textvariable=self.editor_name, wraplength=290).grid(row=0, column=0, columnspan=2, sticky='w')
        for i, (key, label) in enumerate([('width', '画面宽度'), ('height', '画面高度'), ('x', '屏幕 X'), ('y', '屏幕 Y')]):
            cell = ttk.Frame(editor)
            cell.grid(row=1+i//2, column=i%2, sticky='ew', padx=(0, 5), pady=4)
            ttk.Label(cell, text=label, style='Muted.TLabel').pack(anchor='w')
            ttk.Entry(cell, textvariable=self.editor_vars[key], width=12).pack(fill='x')
        ttk.Button(editor, text='保存此角色窗口配置', command=self.save_editor).grid(row=3, column=0, columnspan=2, sticky='ew', pady=5)
        ttk.Button(editor, text='使用统一尺寸', command=self.reset_editor).grid(row=4, column=0, columnspan=2, sticky='ew')
        self.preview_info = tk.StringVar(value='勾选角色以预览排列')
        ttk.Label(card, textvariable=self.preview_info, wraplength=320, style='Muted.TLabel').pack(anchor='w', pady=(8, 0))

    def refresh_groups(self):
        groups = sorted(set(['未分组'] + self.config().get('groups', []) + [a.get('group') or '未分组' for a in self.tree.all_roles()]))
        self.group_combo.configure(values=groups)
        self.tree.regroup()

    def new_group(self):
        name = simpledialog.askstring('新建分组', '分组名称：', parent=self.window)
        if name and name.strip():
            name = name.strip()
            self.save({**self.config(), 'groups': sorted(set(self.config().get('groups', []) + [name]))})
            self.group.set(name)
            self.refresh_groups()

    def assign_group(self):
        ids = set(self.tree.selection() or self.tree.launch_ids())
        if not ids:
            return
        self.save({**self.config(), **{key: [{**a, 'group': self.group.get()} if a['id'] in ids else a for a in self.config().get(key, [])] for key in ('accounts', 'pending')}})
        self.refresh_groups()

    def rename_group(self):
        old = self.group.get()
        if old == '未分组':
            return
        name = simpledialog.askstring('重命名分组', '新的分组名称：', initialvalue=old, parent=self.window)
        if not name or not name.strip() or name.strip() == old:
            return
        self.replace_group(old, name.strip())

    def remove_group(self):
        old = self.group.get()
        if old != '未分组':
            self.replace_group(old, '未分组')

    def replace_group(self, old, new):
        data = self.config()
        self.save({**data, 'groups': sorted(set([g for g in data.get('groups', []) if g != old] + [new])),
                   **{key: [{**a, 'group': new} if a.get('group') == old else a for a in data.get(key, [])] for key in ('accounts', 'pending')}})
        old_key = self.tree.group_parent(old)
        self.group.set(new)
        self.refresh_groups()
        if self.tree.exists(old_key) and not self.tree.get_children(old_key):
            self.tree.delete(old_key)

    def settings(self):
        return {**{key: int(self.vars[key].get()) for key in ('width', 'height', 'columns', 'gap', 'padding')},
                'mode': self.vars['mode'].get(), 'aspect': self.aspect.get()}

    def refresh_screens(self):
        old = self.monitor.get()
        self.monitors = window_layout.screens()
        labels = [f'{i+1}. {m["work"][2]} × {m["work"][3]}' + (' · 主屏' if m['primary'] else '') for i, m in enumerate(self.monitors)]
        self.screen_combo.configure(values=labels)
        if labels:
            self.monitor.set(old if old in labels else labels[0])
        self.preview()

    def work(self):
        if not self.monitors:
            raise ValueError('未发现可用屏幕')
        index = self.screen_combo.current()
        return self.monitors[max(0, index)]['work']

    def preview(self):
        if not hasattr(self, 'canvas'):
            return
        self.canvas.delete('all')
        try:
            ids = self.tree.launch_ids()
            work = self.work()
            rects = self.layout(ids)
            self.last_rects = rects
            cw, ch = max(100, self.canvas.winfo_width()), 185
            scale = min((cw-28)/work[2], (ch-24)/work[3])
            ox, oy = (cw-work[2]*scale)/2, (ch-work[3]*scale)/2
            self.preview_transform = (scale, ox, oy, work)
            self.canvas.create_rectangle(ox, oy, ox+work[2]*scale, oy+work[3]*scale, outline='#d8b988')
            for i, (key, r) in enumerate(rects.items()):
                x, y, w, h = r
                a, b = ox+(x-work[0])*scale, oy+(y-work[1])*scale
                self.canvas.create_rectangle(a, b, a+w*scale, b+h*scale, fill='#78503d' if key in self.tree.selection() else '#485461', outline='#f2c98e', tags=('role:'+key,))
                name = next((v.get('nickname') or v.get('name') for v in self.tree.all_roles() if v['id'] == key), str(i+1))
                self.canvas.create_text(a+5, b+5, text=f'{i+1} {name}', fill='white', anchor='nw', width=max(20, w*scale-8), font=('Microsoft YaHei UI', 8), tags=('role:'+key,))
            self.preview_info.set(f'{len(ids)} 个窗口 · 点击选中，拖动保存自定义坐标。未运行时为画面示意；点击排列后才移动游戏。')
        except (ValueError, tk.TclError) as error:
            self.preview_info.set(str(error))

    def layout(self, ids):
        frame = (0, 0)
        for key in ids:
            try:
                frame = window_layout.border(self.state(key), self.stamp)
                break
            except (OSError, ValueError):
                pass
        self.last_frame = frame
        return window_layout.profile_rectangles(ids, self.work(), self.profiles, frame=frame, **self.settings())

    def load_editor(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            self.editor_name.set('选中一个角色编辑独立窗口')
            return
        key = selected[0]
        role = next(a for a in self.tree.all_roles() if a['id'] == key)
        self.editor_name.set(role.get('nickname') or role.get('name') or key)
        item = self.profiles.get(key, {})
        rect = self.last_rects.get(key, (self.work()[0], self.work()[1], 0, 0))
        for name in ('width', 'height', 'x', 'y'):
            self.editor_vars[name].set(str(item.get(name, self.vars[name].get() if name in ('width', 'height') else rect[0 if name == 'x' else 1])))

    def save_editor(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        key = selected[0]
        before = dict(self.profiles)
        try:
            self.profiles[key] = {k: int(v.get()) for k, v in self.editor_vars.items()}
            self.layout(list(dict.fromkeys(list(self.tree.launch_ids()) + [key])))
            self.save({**self.config(), 'window_profiles': self.profiles})
            self.preview()
            self.note('已保存所选角色的独立尺寸与坐标；自定义模式使用 X / Y。')
        except (OSError, ValueError) as error:
            self.profiles = before
            messagebox.showerror('未保存窗口配置', str(error), parent=self.window)

    def reset_editor(self):
        for key in self.tree.selection():
            self.profiles.pop(key, None)
        self.save({**self.config(), 'window_profiles': self.profiles})
        self.preview()
        self.load_editor()

    def preview_press(self, event):
        for item in reversed(self.canvas.find_overlapping(event.x, event.y, event.x, event.y)):
            tag = next((t for t in self.canvas.gettags(item) if t.startswith('role:')), None)
            if tag:
                key = tag[5:]
                self.tree.selection_set(key)
                self.tree.see(key)
                self.load_editor()
                self.drag = (key, event.x, event.y, dict(self.last_rects), False)
                return

    def preview_drag(self, event):
        if not self.drag:
            return
        key, sx, sy, original, moved = self.drag
        if not moved and abs(event.x-sx)+abs(event.y-sy) < 4:
            return
        if not moved:
            fw, fh = self.last_frame
            for role_id, rect in original.items():
                self.profiles[role_id] = {'x': rect[0], 'y': rect[1], 'width': rect[2]-fw, 'height': rect[3]-fh}
            self.vars['mode'].set('自定义坐标')
        scale, ox, oy, work = self.preview_transform
        x, y, w, h = original[key]
        self.profiles[key]['x'] = max(work[0], min(work[0]+work[2]-w, round(x+(event.x-sx)/scale)))
        self.profiles[key]['y'] = max(work[1], min(work[1]+work[3]-h, round(y+(event.y-sy)/scale)))
        self.drag = (key, sx, sy, original, True)
        self.preview()
        self.load_editor()

    def preview_release(self, event):
        if self.drag and self.drag[-1]:
            try:
                self.save({**self.config(), 'window_profiles': self.profiles})
                self.note('已保存自定义位置；点击排列按钮应用到游戏窗口。')
            except OSError as error:
                messagebox.showerror('位置未保存', str(error), parent=self.window)
        self.drag = None

    def save_plan(self):
        try:
            name = self.plan_name.get().strip()
            if not name:
                raise ValueError('请填写方案名称')
            settings = self.settings()
            self.layout(self.tree.launch_ids() or ['validation'])
            plan = {'settings': settings, 'auto': self.auto.get(), 'screen': self.monitor.get(), 'roles': list(self.tree.launch_ids()), 'windows': {k: dict(v) for k, v in self.profiles.items()}}
            self.save({**self.config(), 'layout_plans': {**self.config().get('layout_plans', {}), name: plan}})
            self.plan_combo.configure(values=list(self.config()['layout_plans']))
            self.note(f'已保存排列方案：{name}')
        except (ValueError, OSError) as error:
            messagebox.showerror('未保存方案', str(error), parent=self.window)

    def load_plan(self):
        plan = self.config().get('layout_plans', {}).get(self.plan_name.get())
        if not plan:
            return
        self.profiles = {k: dict(v) for k, v in self.config().get('window_profiles', {}).items()}
        self.profiles.update({k: dict(v) for k, v in plan.get('windows', {}).items()})
        for key, value in plan['settings'].items():
            if key in self.vars:
                self.vars[key].set(str(value))
        self.aspect.set(plan['settings'].get('aspect', True))
        self.auto.set(plan.get('auto', False))
        if plan.get('screen') in self.screen_combo.cget('values'):
            self.monitor.set(plan['screen'])
        self.tree.set_checked(plan.get('roles', []))
        self.preview()

    def remove_plan(self):
        plans = dict(self.config().get('layout_plans', {}))
        plans.pop(self.plan_name.get(), None)
        self.save({**self.config(), 'layout_plans': plans})
        self.plan_combo.configure(values=list(plans))

    def arrange(self):
        try:
            states = {}
            for key in self.tree.launch_ids():
                state = self.state(key)
                try:
                    window_layout.guarded_window(state, self.stamp)
                    states[key] = state
                except (OSError, ValueError):
                    pass
            if not states:
                raise ValueError('所选角色没有可排列的已跟踪游戏窗口')
            rects = self.layout(self.tree.launch_ids())
            moved = 0
            for key, state in states.items():
                rect = rects[key]
                try:
                    self.positions[key] = window_layout.act(state, self.stamp, rectangle=rect)
                    moved += 1
                except (OSError, ValueError) as error:
                    self.note(str(error))
            self.save({**self.config(), 'last_window_positions': self.positions})
            self.note(f'已排列 {moved} 个已跟踪窗口')
        except (ValueError, OSError) as error:
            messagebox.showinfo('排列提示', str(error), parent=self.window)

    def restore(self):
        count = 0
        for key, rect in self.config().get('last_window_positions', {}).items():
            try:
                window_layout.act(self.state(key), self.stamp, rectangle=rect)
                count += 1
            except (OSError, ValueError):
                pass
        self.note(f'已恢复 {count} 个已跟踪窗口的位置')

    def close_ids(self, ids):
        count = 0
        for key in ids:
            try:
                window_layout.act(self.state(key), self.stamp, close=True)
                count += 1
            except (OSError, ValueError):
                pass
        self.note(f'已向 {count} 个已跟踪窗口发送正常关闭请求；如游戏提示确认，请在游戏中处理。')

    def close_selected(self):
        self.close_ids(self.tree.launch_ids())

    def close_all(self):
        self.close_ids([a['id'] for a in self.tree.all_roles()])

    def on_launch(self, key, attempts=20):
        try:
            role = next(a for a in self.tree.all_roles() if a['id'] == key)
            name = role.get('nickname') or role.get('name') or '阴阳师'
            title = name + (' · ' + role['server'] if role.get('server') else '')
            window_layout.act(self.state(key), self.stamp, title=title)
            self.titled.add(key)
            if self.auto.get() and role.get('confirmed'):
                self.arrange()
        except (OSError, ValueError, StopIteration):
            if attempts:
                self.window.after(2000, lambda: self.on_launch(key, attempts-1))

    def tick(self):
        running = 0
        active = set()
        for role in self.tree.all_roles():
            try:
                state = self.state(role['id'])
                if state.get('pid') and self.stamp(state['pid']) == state.get('stamp'):
                    running += 1
                    active.add(role['id'])
                    if self.tree.exists(role['id']):
                        self.tree.set(role['id'], 'state', f'运行中 · PID {state["pid"]}')
            except (OSError, ValueError):
                pass
        for key in self.was_running - active:
            if self.tree.exists(key):
                self.tree.set(key, 'state', '游戏已退出')
        self.was_running = active
        self.tree.update_groups()
        self.count.set(f'{len(self.tree.all_roles())} 个角色 · 勾选 {len(self.tree.checked)} · 运行 {running}')
        self.window.after(3000, self.tick)
