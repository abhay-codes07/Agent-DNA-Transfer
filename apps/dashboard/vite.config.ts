import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev`, proxy the API to a running Helix daemon (`helix dashboard`
// serves the stdlib UI + JSON API on 127.0.0.1:8787).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8787",
    },
  },
});
