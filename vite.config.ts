import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes to ../frontend/index.js so the plugin package ships a
// ready-to-load frontend bundle (no build step needed at install time).
export default defineConfig({
  plugins: [react({ jsxRuntime: "classic" })],
  build: {
    outDir: "frontend",
    emptyOutDir: true,
    lib: {
      entry: "src/index.tsx",
      formats: ["es"],
      fileName: () => "index.js",
    },
    rollupOptions: {
      external: ["react", "react-dom"],
    },
  },
});
