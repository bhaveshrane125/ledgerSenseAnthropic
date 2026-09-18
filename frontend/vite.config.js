import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Build output lands in the Flask package's static/ folder so `create_app()`
// can serve it directly; base "" keeps asset URLs relative so the app works
// mounted at "/".
export default defineConfig({
  plugins: [react()],
  base: "",
  build: {
    outDir: "../src/ledgersense/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
