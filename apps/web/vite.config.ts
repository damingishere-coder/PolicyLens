import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  root: __dirname,
  base: "/",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false
  },
  server: {
    host: "127.0.0.1",
    port: 41731,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8768",
      "/health": "http://127.0.0.1:8768"
    }
  }
});
