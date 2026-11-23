// Keep bridge calls short while the host reads game processes in the background.
export async function backgroundRead(kind,request){
 const api=window.pywebview.api;
 const started=await api.data_read_job('start',{kind,request});
 if(!started.ok)throw Error(started.error);
 const id=started.data.id;
 while(true){
  await new Promise(resolve=>setTimeout(resolve,250));
  const response=await api.data_read_job('status',{id});
  if(!response.ok)throw Error(response.error);
  if(response.data.state==='finished'){
   const reply=response.data.reply;
   if(!reply.ok)throw Error(reply.error);
   return reply.data;
  }
 }
}
