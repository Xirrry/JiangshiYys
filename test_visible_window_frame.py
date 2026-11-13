from ctypes import wintypes as W
from unittest.mock import patch,MagicMock
import window_layout as l
outer=W.RECT(0,0,960,570);visible=W.RECT(7,0,953,563)
a=l.outer_for_visible((0,0,946,563),outer,visible)
b=l.outer_for_visible((946,0,946,563),outer,visible)
assert a==(-7,0,960,570) and b==(939,0,960,570)
assert a[0]+960-7==b[0]+7
for gap in (0,8,20):
 rects=l.profile_rectangles(['a','b'],(0,0,1920,1080),{},frame=(2,32),width=944,height=531,columns=2,gap=gap,padding=0,aspect=True)
 assert rects['b'][0]-(rects['a'][0]+rects['a'][2])==gap
 native=[l.outer_for_visible(r,outer,visible) for r in rects.values()]
 assert native[1][0]+7-(native[0][0]+native[0][2]-7)==gap
assert l.outer_for_visible((0,0,960,570),outer,outer)==(0,0,960,570)
# Actual mutation uses corrected native coordinates while reporting visible bounds.
u=MagicMock();u.SetWindowPos.return_value=1
u.GetWindowThreadProcessId.side_effect=lambda hwnd,owner:setattr(owner._obj,'value',1)
with patch.object(l,'guarded_window',return_value=100),patch.object(l,'api',return_value=u),patch.object(l,'visible_bounds',return_value=(outer,visible)):
 result=l.act({'pid':1,'stamp':10},lambda pid:10,rectangle=(946,0,946,563))
 assert u.SetWindowPos.call_args.args[2:6]==(939,0,960,570)
print('PASS: invisible border compensation, exact zero/positive gaps, unchanged client size, native coordinate conversion and no-DWM fallback.')
