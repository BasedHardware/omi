import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Ship mode serves dist/ from the shell's origin (ADR-009: interception on
// mobile, loopback on macOS) — relative base so assets resolve anywhere.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", sourcemap: true },
});
