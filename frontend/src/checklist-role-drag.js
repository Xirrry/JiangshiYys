import {ref} from 'vue';

// Keep roles and groups as separate drag sources: the ungrouped group uses ''.
export function useRoleGroupDrag(action){
 const dragged=ref(''),hovered=ref(''),after=ref(false),hoverGroup=ref(null),saving=ref(false),error=ref('');
 const groupDragged=ref(null),groupHovered=ref(null),groupAfter=ref(false);
 let suppressUntil=0;
 const active=()=>!!dragged.value||groupDragged.value!==null;
 function clear(){
  if(active())suppressUntil=Date.now()+350;
  dragged.value='';hovered.value='';after.value=false;hoverGroup.value=null;
  groupDragged.value=null;groupHovered.value=null;groupAfter.value=false;
 }
 function click(event){
  if(active()||saving.value||Date.now()<suppressUntil){event.preventDefault();event.stopPropagation();return false}
  return true;
 }
 function begin(event,key,isGroup){
  if(saving.value){event.preventDefault();return}
  clear();error.value='';
  if(isGroup)groupDragged.value=key;else dragged.value=key;
  event.stopPropagation();
  if(event.dataTransfer){event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',key||'ungrouped')}
 }
 function start(event,key){begin(event,key,false)}
 function startGroup(event,id){begin(event,id,true)}
 function accept(event){event.preventDefault();event.stopPropagation();if(event.dataTransfer)event.dataTransfer.dropEffect='move'}
 const below=(event)=>{const box=event.currentTarget.getBoundingClientRect();return event.clientY>box.top+box.height/2};
 function overRole(event,key){
  if(!dragged.value||saving.value||key===dragged.value)return;
  accept(event);after.value=below(event);hovered.value=key;hoverGroup.value=null;
 }
 function overGroup(event,id){
  if(!active()||saving.value)return;
  if(groupDragged.value!==null){
   if(id===groupDragged.value){groupHovered.value=null;return}
   accept(event);groupHovered.value=id;groupAfter.value=below(event);hoverGroup.value=null;hovered.value='';
  }else{accept(event);hovered.value='';hoverGroup.value=id}
 }
 async function drop(event,id,anchor=null){
  if(!active()||saving.value)return;
  accept(event);
  let payload;
  if(groupDragged.value!==null){
   // Group moves are accepted only by a group header that has received dragover.
   if(anchor!==null||id===groupDragged.value||groupHovered.value!==id){clear();return}
   payload={action:'group_move',id:groupDragged.value,before:id,after:groupAfter.value};
  }else{
   if(anchor===dragged.value){clear();return}
   payload={action:'move_role',role:dragged.value,id,anchor,after:anchor?after.value:false};
  }
  clear();saving.value=true;error.value='';
  try{return (await action(payload))!==false}
  catch(e){error.value=e?.message||'保存排序失败，请重试';return false}
  finally{saving.value=false;suppressUntil=Date.now()+350}
 }
 return {dragged,hovered,after,hoverGroup,saving,error,groupDragged,groupHovered,groupAfter,start,startGroup,overRole,overGroup,drop,clear,click};
}

export const useChecklistRoleDrag=useRoleGroupDrag;
