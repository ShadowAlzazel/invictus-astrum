import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// dev server proxies to `python serve.py` (port from config.toml [server])
export default defineConfig({
  plugins: [svelte()],
  server: { proxy: { '/api': 'http://127.0.0.1:8010', '/ws': { target: 'ws://127.0.0.1:8010', ws: true } } },
});
