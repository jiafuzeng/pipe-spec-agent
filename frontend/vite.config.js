import { defineConfig } from "vite";

const proxy = {
  "/api/": {
    target: process.env.API_UPSTREAM || "http://127.0.0.1:8000",
    changeOrigin: true,
  },
};

export default defineConfig({
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
});
