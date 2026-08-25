import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Kept separate from vite.config.ts so the production build config stays
// exactly what it was -- nothing here can affect `npm run build`.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    restoreMocks: true,
  },
});
