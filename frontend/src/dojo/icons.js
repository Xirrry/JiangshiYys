const items=import.meta.glob('./icons/*.png',{eager:true,import:'default',query:'?url'});
const mapping={490002:'broken_amulet',900007:'hyakki_ticket',410:'daruma_contract',490001:'mystery_amulet',900001:'coin',900090:'contrib',900016:'medal'};
export function resourceIcon(id){return items['./icons/'+(mapping[id]||String(id))+'.png']||null;}
