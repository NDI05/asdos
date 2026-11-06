import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  plugins: [react()],
  preview: {
    proxy: { "/api": { target: process.env.ASDOS_API_URL ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  server: {
    proxy: { "/api": { target: process.env.ASDOS_API_URL ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { sourcemap: false },
});
