// Map legacy CSS colors to shared roles, retaining exact defaults for warm paper.
function colorRole(hex, property, selector) {
  let raw = hex.slice(1);
  if (raw.length <= 4) raw = [...raw].map(c => c + c).join('');
  const rgb = [0, 2, 4].map(i => parseInt(raw.slice(i, i + 2), 16) / 255);
  const high = Math.max(...rgb), low = Math.min(...rgb), light = (high + low) / 2;
  let role;
  const text = property === 'color' || property === 'fill' || property === 'stroke';
  if (text) role = light > .74 ? 'on-accent' : light < .36 ? 'text' : 'muted';
  else if (/border|outline/.test(property)) role = light > .7 ? 'border' : 'accent';
  else if (/shadow/.test(property)) role = 'shadow';
  else role = light > .965 ? 'surface' : light > .93 ? 'base' : light > .86 ? 'raised' : light > .65 ? 'selection' : light < .27 ? 'stage' : 'accent';
  if (/error|danger|failed|failure/.test(selector)) {
    if (text || light < .65) role = 'danger';
  } else if (/success/.test(selector) && text) {
    role = 'success';
  }
  if (!text && !/border|outline|shadow/.test(property) && /\.active|\.selected|\.picked|\.chosen/.test(selector) && light > .6) role = 'selection';
  const opaque = '#' + raw.slice(0, 6);
  const value = `var(--skin-${role}, ${opaque})`;
  if (raw.length === 8) {
    const alpha = parseInt(raw.slice(6), 16) / 255 * 100;
    return `color-mix(in srgb, ${value} ${alpha.toFixed(2)}%, transparent)`;
  }
  return value;
}
export default function skinColors() {
  const handled = new WeakSet();
  return {postcssPlugin:'launcher-skin-colors', Declaration(decl) {
    if (handled.has(decl)) return;
    handled.add(decl);
    if (decl.prop.startsWith('--') || !/#(?:[0-9a-f]{3,8})\b/i.test(decl.value)) return;
    decl.value = decl.value.replace(/#[0-9a-f]{8}\b|#[0-9a-f]{6}\b|#[0-9a-f]{4}\b|#[0-9a-f]{3}\b/gi, hex => colorRole(hex,decl.prop,decl.parent?.selector||''));
  }};
}
