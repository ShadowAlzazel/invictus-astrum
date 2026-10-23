<script>
  // Signing in (astrum/accounts.py): a name and a password, checked by the server, which keeps the
  // session in a cookie. Basic, for a local network: the users are data/users.toml.
  import { api } from './api.js';

  export let onsigned = () => {};      // (user)

  let name = '', password = '', problem = '', busy = false;
  async function submit() {
    busy = true; problem = '';
    try { onsigned((await api.signIn(name, password)).user); }
    catch (err) { problem = String(err.message ?? err); }
    finally { busy = false; }
  }
</script>

<aside data-ui>
  <p class="brand">INVICTUS <b>ASTRUM</b></p>
  <h1>Sign in</h1>
  <form on:submit|preventDefault={submit}>
    <label for="signin-name">Name</label>
    <input id="signin-name" bind:value={name} autocomplete="username" autofocus />
    <label for="signin-password">Password</label>
    <input id="signin-password" type="password" bind:value={password} autocomplete="current-password" />
    {#if problem}<p class="problem">{problem}</p>{/if}
    <button class="enter" type="submit" disabled={busy || !name}>Sign in ▸</button>
  </form>
  <p class="keys">The users are data/users.toml on the server. Add one with python -m astrum.accounts NAME PASSWORD</p>
</aside>

<style>
  aside {
    position: fixed; top: 20px; left: 20px; width: 340px; z-index: 25;
    background: var(--panel); border-left: 1px solid var(--violet); padding: 18px 20px; backdrop-filter: blur(6px);
  }
  .brand { font-family: var(--display); letter-spacing: 0.14em; color: var(--dim); margin: 0; font-size: 12px; }
  .brand b { color: var(--ink); font-weight: 600; }
  h1 { font-family: var(--display); font-weight: 600; font-size: 26px; margin: 10px 0 16px; }
  form { display: grid; gap: 6px; }
  label { color: var(--dim); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }
  input { background: rgba(0, 0, 0, 0.3); border: 1px solid var(--rule); color: var(--ink); font: inherit; padding: 6px 8px; margin-bottom: 8px; }
  input:focus { outline: none; border-color: var(--fuchsia); }
  .problem { color: #ffd27a; font-size: 12px; margin: 0 0 6px; }
  .enter { justify-self: start; background: none; border: 0; padding: 0; color: var(--ink); font-family: var(--display); font-size: 15px; box-shadow: inset 0 -1px 0 var(--fuchsia); }
  .enter:disabled { color: var(--dim); box-shadow: none; }
  .keys { color: var(--dim); font-size: 10px; margin: 16px 0 0; line-height: 1.4; }
</style>
