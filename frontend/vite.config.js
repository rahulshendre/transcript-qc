import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built page is served by the Python app from transcript_qc/web/static.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "../transcript_qc/web/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { environment: "node" },
});
