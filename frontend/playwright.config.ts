import { defineConfig, devices } from "@playwright/test"

const apiPort = 18_000
const frontendPort = 15_173
const apiUrl = `http://127.0.0.1:${apiPort}`

export default defineConfig({
  testDir: "./tests",
  testMatch: /workbench\.spec\.ts/,
  timeout: 90_000,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? "blob" : "list",
  use: {
    baseURL: `http://127.0.0.1:${frontendPort}`,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile",
      use: {
        ...devices["Pixel 5"],
        viewport: { width: 390, height: 844 },
      },
    },
  ],
  webServer: [
    {
      command: `cd .. && WORKBENCH_LLM_MODE=offline WORKBENCH_API_PORT=${apiPort} WORKBENCH_FRONTEND_PORT=${frontendPort} WORKBENCH_DATA_DIR=$(mktemp -d) .venv/bin/python scripts/dev-workbench-api.py`,
      url: `${apiUrl}/openapi.json`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `VITE_API_URL=${apiUrl} npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      url: `http://127.0.0.1:${frontendPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
