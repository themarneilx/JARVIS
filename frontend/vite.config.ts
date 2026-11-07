import { defineConfig } from "vite";
export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: Number(process.env.JARVIS_FRONTEND_PORT || 3000),
    strictPort: true,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.JARVIS_PORT || 8787}`,
        changeOrigin: false,
      },
    },
  },
  build: { chunkSizeWarningLimit: 1300 },
});
