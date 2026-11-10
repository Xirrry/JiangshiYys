export function cloneJson(value) { return JSON.parse(JSON.stringify(value)); }


// Replace dimensions for selected roles only; retain their custom coordinates.
export function applyRoleSizes(profiles, ids, draft, aspect) {
  const width = Number(draft.width), rawHeight = Number(draft.height);
  const height = aspect ? Math.round(width * 9 / 16) : rawHeight;
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 160 || height < 90)
    throw Error('游戏窗口尺寸需为整数，至少 160 × 90');
  const result = cloneJson(profiles);
  for (const id of ids) result[id] = {...result[id], width, height};
  return result;
}


export function reorderMembers(ids, from, target, after = false) {
  if (from === target || !ids.includes(from) || !ids.includes(target)) return [...ids];
  const result = ids.filter(id => id !== from);
  result.splice(result.indexOf(target) + (after ? 1 : 0), 0, from);
  return result;
}
