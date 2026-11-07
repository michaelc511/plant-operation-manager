/// <reference types="vitest" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The browser calls /api/*; Vite forwards it to FastAPI. A phone on the same Wi-Fi therefore only
// needs to reach this server, and the backend URL is never baked into the app.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.API_PROXY_TARGET || "http://localhost:8000";
  const proxy = {
    "/api": { target, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, "") },
  };
  return {
    plugins: [react()],
    server: { port: 5173, proxy },
    preview: { port: 4173, proxy },
    test: { environment: "jsdom", include: ["tests/**/*.test.{ts,tsx}"] },
  };
});
