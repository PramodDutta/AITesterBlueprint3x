import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  retries: 0,                       // the AGENT decides about retries, not the runner
  use: { browserName: "chromium" },
});
