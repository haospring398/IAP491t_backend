import { defineConfig, devices } from "@playwright/test";
const testDev = process.env.FRONTEND_TEST_DEV === "1";
export default defineConfig({
  testDir: "./tests/browser", fullyParallel: false, workers: 1,
  timeout: 30000, reporter: "list",
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: process.env.PLAYWRIGHT_CHANNEL } }],
  webServer: { command: `node node_modules/next/dist/bin/next ${testDev ? "dev" : "start"} --hostname 127.0.0.1 --port 3100`, url: "http://127.0.0.1:3100", timeout: 60000, reuseExistingServer: false, env: { ML_API_URL: "", ML_API_TOKEN: "" } },
});
