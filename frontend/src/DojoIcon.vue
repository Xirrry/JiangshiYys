<script setup>
import {resourceIcon,resourceIconIsPlaceholder} from './dojo/icons.js';defineProps({id:Number});
</script><template><img v-if="resourceIcon(id)" :src="resourceIcon(id)" alt="" :title="resourceIconIsPlaceholder(id)?'暂用示意图，待补原图':undefined" class="dojo-item-icon"></template><style scoped>.dojo-item-icon{width:28px;height:28px;object-fit:contain;flex:none;vertical-align:middle;margin-right:8px}</style>
