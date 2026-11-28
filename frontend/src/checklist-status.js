// The free daily gift must be claimed to advance its recurring reward cycle.
export function isTaskComplete(task){
 return task.status==='done'||(task.status==='claimable'&&task.id!=='d3');
}
