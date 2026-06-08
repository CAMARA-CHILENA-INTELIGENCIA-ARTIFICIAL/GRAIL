import { defineConfig } from 'vite'
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // The D3 renderer core lives in grail/viz/web/src and is compiled
      // straight from source by vite — no separate build step needed.
      // From grail/apps/chat/frontend, climb three levels to reach grail/.
      '@grail/viz': resolve(__dirname, '../../../viz/web/src/index.ts'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
    fs: {
      // Allow vite to import the renderer source that lives outside the
      // chat frontend's own root (it's two packages up).
      allow: [
        resolve(__dirname),
        resolve(__dirname, '../../../viz/web'),
      ],
    },
  },
})
