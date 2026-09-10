import { defineConfig } from "vite";

// No GitHub Pages o site fica em https://<user>.github.io/bdgd-light/ → VITE_BASE=/bdgd-light/
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  // maplibre-gl sozinho passa de 800 kB; é um único chunk servido com cache longo pelo Pages
  build: { target: "es2022", sourcemap: false, chunkSizeWarningLimit: 1200 },
  // `npm run dev` fala com `bdgd-light serve` (porta 8000) na mesma origem, sem ?api=
  server: {
    port: 5173,
    open: false,
    proxy: { "/api": { target: process.env.BDGD_API ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
