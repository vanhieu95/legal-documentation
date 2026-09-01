const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests/browser",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  outputDir: "test-results",
  use: {
    baseURL: "http://127.0.0.1:8000",
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
    video: "off",
  },
  webServer: {
    command: ".venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload",
    url: "http://127.0.0.1:8000/health/live/",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
