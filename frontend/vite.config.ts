/// <reference types="vitest" />
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The browser calls /api/*; Vite forwards it to FastAPI. A phone on the same Wi-Fi therefore only
// needs to reach this server, and the backend URL is never baked into the app.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.API_PROXY_TARGET || "http://localhost:8000";
  const proxy = {
    "/api": { target, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, "") },
  };
  // /home serves the static "Ops Now" home page, as FastAPI does in the deployed app.
  const toHome = (req: unknown, _res: unknown, next: () => void) => {
    const r = req as { url?: string };
    if (r.url === "/home" || r.url?.startsWith("/home?")) r.url = r.url.replace("/home", "/home.html");
    next();
  };
  const homeRoute: Plugin = {
    name: "home-route",
    configureServer: (server) => void server.middlewares.use(toHome),
    configurePreviewServer: (server) => void server.middlewares.use(toHome),
  };
  return {
    plugins: [react(), homeRoute],
    server: { port: 5173, proxy },
    preview: { port: 4173, proxy },
    test: { environment: "jsdom", include: ["tests/**/*.test.{ts,tsx}"] },
  };
});
