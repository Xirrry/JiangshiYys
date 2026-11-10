"""Explicit, user-confirmed single-profile cleanup. Never follow resource links.

Inspection is read-only. Execution names one file/link/directory per operation;
there are no recursive removal calls or shell commands. Never run automatically.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

REPARSE=0x400
MOUNT_POINT=0xA0000003
SYMLINK=0xA000000C


def kind(path,info):
    if getattr(info,'st_file_attributes',0)&REPARSE:
        tag=getattr(info,'st_reparse_tag',0)
        if tag==MOUNT_POINT:return 'junction'
        if tag==SYMLINK:return 'symlink'
        raise ValueError('缓存含不支持的重解析点，已停止：'+str(path))
    if stat.S_ISLNK(info.st_mode):return 'symlink'
    if stat.S_ISDIR(info.st_mode):return 'directory'
    if stat.S_ISREG(info.st_mode):return 'file'
    raise ValueError('缓存中存在不支持的文件类型：'+str(path))


def anchor(base,root):
    base=Path(base).absolute();root=Path(root).absolute()
    if root.parent!=base or root==base:
        raise ValueError('只能清理 profiles 下的一个角色私有目录')
    # Refuse a redirected data/profiles ancestor before inspecting any contents.
    for parent in [base,*base.parents]:
        if os.path.lexists(parent) and kind(parent,parent.lstat())!='directory':
            raise ValueError('缓存父目录不能是链接或文件：'+str(parent))
    if os.path.lexists(root) and kind(root,root.lstat())!='directory':
        raise ValueError('角色私有根目录不能是链接或文件')
    return base,root


def identity(info):
    return [info.st_dev,info.st_ino]


def inspect(base,root):
    base,root=anchor(base,root);entries=[];logical=0;shared_links=0;hardlinks=0
    def visit(path):
        nonlocal logical,shared_links,hardlinks
        info=path.lstat();entry_kind=kind(path,info)
        if entry_kind=='directory':
            with os.scandir(path) as listing:
                children=sorted((Path(entry.path) for entry in listing),key=lambda p:p.name.casefold())
            for child in children:visit(child)
        size=info.st_size if entry_kind=='file' else 0
        if entry_kind=='file':
            if info.st_nlink<=1:logical+=size
            else:hardlinks+=1
        elif entry_kind in ('junction','symlink'):shared_links+=1
        entries.append({'path':str(path.relative_to(root)),'kind':entry_kind,'identity':identity(info),
                        'size':size,'mtime':info.st_mtime_ns,'links':info.st_nlink})
    if os.path.lexists(root):visit(root)
    signature=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest()
    return {'root':str(root),'signature':signature,'entries':entries,'bytes':logical,
            'files':sum(row['kind']=='file' for row in entries),'resource_links':shared_links,'hardlinked_files':hardlinks}


def execute(base,plan):
    base,root=anchor(base,Path(plan['root']))
    current=inspect(base,root)
    if current['signature']!=plan['signature']:
        raise ValueError('缓存内容已变化，请重新打开删除确认窗口')
    removed=0
    for row in plan['entries']:
        relative=Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('清理路径越界')
        target=root/relative
        if target!=root and not target.is_relative_to(root):raise ValueError('清理路径越界')
        # Recheck ancestors and object identity immediately before each operation.
        parent=target.parent
        while parent!=base:
            if kind(parent,parent.lstat())!='directory':raise ValueError('清理过程中目录变为链接，已停止')
            parent=parent.parent
        info=target.lstat()
        if identity(info)!=row['identity'] or kind(target,info)!=row['kind']:
            raise ValueError('缓存文件已被替换，已停止')
        if row['kind']=='file' and (info.st_size!=row['size'] or info.st_mtime_ns!=row['mtime']):
            raise ValueError('缓存仍在写入，已停止')
        if row['kind'] in ('directory','junction'):
            # On Windows, rmdir of a junction removes only that junction itself.
            os.rmdir(target)
        else:
            os.unlink(target)
        removed+=1
    return {'bytes':plan['bytes'],'files':plan['files'],'removed_entries':removed}
