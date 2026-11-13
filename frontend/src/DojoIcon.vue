<script setup>
import {resourceIcon} from './dojo/icons.js';defineProps({id:Number});
</script><template><img v-if="resourceIcon(id)" :src="resourceIcon(id)" alt="" class="dojo-item-icon"></template><style scoped>.dojo-item-icon{width:28px;height:28px;object-fit:contain;flex:none;vertical-align:middle;margin-right:8px}</style>
