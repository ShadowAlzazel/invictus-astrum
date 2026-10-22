// The map's keys: the key each action is bound to, rebound in Settings (Hotkeys) and kept in this
// browser. Esc always cancels, Shift always steps finer; everything else is here.
import { get, writable } from 'svelte/store';

export const ACTIONS = {
  pause:    { key: ' ', label: 'Run or pause the clock' },
  faster:   { key: ']', label: 'Clock faster' },
  slower:   { key: '[', label: 'Clock slower' },
  settings: { key: ',', label: 'Settings' },
  order:    { key: 'm', label: 'Move: order the selection (again: cancel; Shift-click queues)' },
  attack:   { key: 'a', label: 'Attack-move: aggressive the whole way, on after each engagement' },
  patrol:   { key: 'p', label: 'Patrol: to the point and back, over and over, on guard' },
  up:       { key: 'w', label: 'Telegraph up' },
  down:     { key: 's', label: 'Telegraph down' },
  eve:      { key: 'e', label: 'Aim toward Eve' },
  haid:     { key: 'q', label: 'Aim toward Haid' },
  stop:     { key: 'z', label: 'STOP: drop the order, cut the drive, fly on as she goes' },
  decel:    { key: 'x', label: 'DECELERATE: drop the order, turn and burn to rest on the bullseye' },
  ping:     { key: 'v', label: 'Active sensors: ping, or go quiet (a ping shows the pinger)' },
  plane:    { key: 'b', label: "Orders: her own height or the bullseye's plane" },
  ranges:   { key: 'g', label: 'Weapon ranges (hold)' },
  sensing:  { key: 'r', label: 'Detection ranges (hold)' },
  focus:    { key: 'f', label: 'Focus on the selection' },
  home:     { key: 'h', label: 'Frame everything' },
  chain:    { key: 'u', label: 'Up the chain of command' },
  levels:   { key: 'l', label: 'Levels' },
};
const STORE = 'astrum.keys.2';       // (.2: move went to M, ping to V)
const defaults = () => Object.fromEntries(Object.entries(ACTIONS).map(([a, d]) => [a, d.key]));

function load() {
  try { return { ...defaults(), ...JSON.parse(localStorage.getItem(STORE) ?? '{}') }; } catch { return defaults(); }
}
export const keymap = writable(load());
keymap.subscribe((m) => { try { localStorage.setItem(STORE, JSON.stringify(m)); } catch { /* not kept */ } });

// whether a key event is the action's key (letters either case)
export const is = (e, action) => e.key.toLowerCase() === get(keymap)[action];
// how a key reads on a key cap
export const cap = (k) => (k === ' ' ? 'Space' : k.length === 1 ? k.toUpperCase() : k);

// bind an action to a key: an action that had it gives it up (left unbound)
export function bind(action, key) {
  keymap.update((m) => {
    const out = { ...m };
    for (const a of Object.keys(out)) if (out[a] === key) out[a] = '';
    out[action] = key.toLowerCase();
    return out;
  });
}
export const resetKeys = () => keymap.set(defaults());
