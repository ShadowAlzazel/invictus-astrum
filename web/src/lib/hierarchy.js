// What a selection opens in a formation tree: the same rule as astrum/display.py `reveal`,
// over the tree the server sends with each unit (parent, children, ancestors).
export function reveal(byId, selected, sel) {
  const out = { open: new Set(), children: new Set(), parents: new Set() };
  const s = byId[selected];
  if (!s) return out;
  for (const a of s.ancestors ?? []) out.open.add(a);
  let frontier = [selected];
  for (let i = 0; i < (sel?.reveal_children ?? 1); i++) {
    const next = [];
    for (const f of frontier) {
      const kids = byId[f]?.children ?? [];
      if (kids.length) { out.open.add(f); kids.forEach((k) => out.children.add(k)); next.push(...kids); }
    }
    frontier = next;
  }
  if ((sel?.reveal_parent ?? true) && s.parent) out.parents.add(s.parent);
  return out;
}
