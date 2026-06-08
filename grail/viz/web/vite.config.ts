import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      name: "GrailViz",
      formats: ["umd", "es"],
      fileName: (format) => `grail-viz.${format === "umd" ? "umd.cjs" : "es.js"}`,
    },
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith(".css")) return "grail-viz.css";
          return assetInfo.name ?? "asset-[hash][extname]";
        },
      },
    },
    sourcemap: true,
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    open: "/examples/dev.html",
  },
});
