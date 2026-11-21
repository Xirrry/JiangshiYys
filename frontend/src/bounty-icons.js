import {resourceIcon} from './dojo/icons.js';
import icon0 from './bounty-icons/jade-cutout.png';
import icon1 from './bounty-icons/stamina-cutout.png';
import icon2 from './bounty-icons/fish-cutout.png';
import icon3 from './bounty-icons/ribs-cutout.png';
import icon4 from './bounty-icons/shard-low-cutout.png';
import icon5 from './bounty-icons/shard-mid-cutout.png';
import icon6 from './bounty-icons/shard-high-cutout.png';
export const rewardIcons = {
  '金币': {url: new URL(resourceIcon(900001), window.location.href).href},
  '勾玉': {url: new URL(icon0, window.location.href).href},
  '体力': {url: new URL(icon1, window.location.href).href},
  '鲜鱼': {url: new URL(icon2, window.location.href).href},
  '排骨': {url: new URL(icon3, window.location.href).href},
  '随机低级碎片': {url: new URL(icon4, window.location.href).href},
  '随机中级碎片': {url: new URL(icon5, window.location.href).href},
  '随机高级碎片': {url: new URL(icon6, window.location.href).href}
};
