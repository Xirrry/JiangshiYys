"""Important weekly shop offers shown alongside other weekly tasks."""
OFFERS=[('42','勋章商店','御行达摩',411),('shrine_411_2','神龛','御行达摩',411),('22','荣誉商店','蓝票',490001),('25','荣誉商店','御行达摩碎片',434111),('40','勋章商店','蓝票',490001),('704','寮商店','蓝票',490001),('705','寮商店','黑碎礼包',434111),('treasure_1348','千物宝库','蓝票',490001),('treasure_1349','千物宝库','御行达摩碎片',434111)]
OFFERS.append(('1402','寄售屋','寄售券（勾玉兑换）',900338))
TASKS=[{'id':'weekly_shop_'+key,'name':shop+' · '+name,'period':'weekly','lifetime':False,'category':'shop','icon':icon} for key,shop,name,icon in OFFERS]
def observations(goods,balances):
 result={};known={key for key,*_ in OFFERS}
 for g in goods:
  if g.get('key') not in known or g.get('stale') or g.get('cycle') not in ('weekly','period'):continue
  bought,limit,left=(g.get(k) for k in ('bought','limit','remaining'))
  if any(type(x) is not int for x in (bought,limit,left)) or limit<=0 or bought<0 or left<0 or bought+left!=limit:continue
  period='本期' if g['cycle']=='period' else '本周'
  detail=f'{period}已购 {bought} / {limit} 份 · 剩余 {left} 份'
  if g['key']=='1402':detail+=' · 每份100寄售券'
  if left:
   shortages=[];funds=[];missing=False
   costs=g.get('costs',[])
   if not costs:missing=True
   for c in costs:
    wallet=balances.get(str(c.get('id')),{});amount=wallet.get('amount');price=c.get('amount');name=c.get('name') or wallet.get('name') or '货币'
    if type(amount) not in (int,float) or amount<0 or type(price) not in (int,float) or price<=0:missing=True;continue
    need=price*left;funds.append(f'{name} {amount:,.0f} / 需 {need:,.0f}')
    if amount<need:shortages.append(f'{need-amount:,.0f} {name}')
   if funds:detail+=' · '+'；'.join(funds)
   if missing:detail+=' · 余额未读全'
   elif shortages:detail+=' · 还需获取 '+'、'.join(shortages)
  result['weekly_shop_'+g['key']]={'status':'done' if left==0 else 'todo','detail':detail}
 return result
