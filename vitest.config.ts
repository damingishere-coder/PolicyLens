import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/{unit,contract}/**/*.test.ts", "apps/web/src/**/*.test.ts"],
    coverage: { reporter: ["text", "html"] }
  }
});
