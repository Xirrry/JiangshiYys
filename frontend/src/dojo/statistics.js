// A recorded role-day is one observed role on one date, not a completed battle day.
export function summarizeMails(rows) {
  const roleDays = new Set();
  const dates = new Set();
  const roles = new Set();
  const amounts = new Map();
  for (const row of rows) {
    roleDays.add(JSON.stringify([row.role_id, row.date]));
    dates.add(row.date);
    roles.add(row.role_id);
    for (const [id, amount] of row.items) {
      amounts.set(String(id), (amounts.get(String(id)) || 0) + amount);
    }
  }
  const sortedDates = [...dates].sort();
  return {mailCount:rows.length, roleCount:roles.size, dayCount:dates.size,
    roleDayCount:roleDays.size, from:sortedDates[0] || '', to:sortedDates.at(-1) || '',
    amounts:Object.fromEntries(amounts)};
}
export function groupMails(rows, grouping) {
  const groups = new Map();
  for (const row of rows) {
    const key = grouping === 'month' ? row.date.slice(0, 7) : row.role_id;
    if (!groups.has(key)) groups.set(key, {key, label:grouping === 'month' ? key : row.label, rows:[]});
    groups.get(key).rows.push(row);
  }
  return [...groups.values()].map(group => ({key:group.key,label:group.label,...summarizeMails(group.rows)}))
    .sort((a,b) => grouping === 'month' ? b.key.localeCompare(a.key) : a.label.localeCompare(b.label,'zh-CN'));
}
