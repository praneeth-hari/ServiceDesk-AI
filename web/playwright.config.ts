import { defineConfig, devices } from '@playwright/test';

const PORT = process.env.E2E_PORT ?? '8765';

export default defineConfig({
  testDir: './e2e',
  // The tests share one seeded database, so they run one at a time
  workers: 1,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    launchOptions: {
      // Lets a machine with a preinstalled Chromium reuse it (leave unset in CI)
      executablePath: process.env.PW_CHROMIUM_PATH || undefined,
    },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    // Builds nothing: run `npm run build` first so web/dist exists
    command: 'sh scripts/e2e_server.sh',
    cwd: '..',
    url: `http://127.0.0.1:${PORT}/api/v1/health`,
    reuseExistingServer: !process.env.CI,
    stdout: 'ignore',
    timeout: 120_000,
  },
});
