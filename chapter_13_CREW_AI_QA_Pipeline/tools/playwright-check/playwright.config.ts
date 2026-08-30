import { defineConfig } from '@playwright/test';

// Verification harness only: it compiles and lists generated specs, it never
// runs them against a real site. baseURL comes from the environment so no
// environment-specific URL is ever committed.
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    trace: 'off',
  },
});
