const { defineConfig } = require("@playwright/test");

const port = process.env.PLAYWRIGHT_PORT || "8000";
const baseURL = `http://127.0.0.1:${port}`;

module.exports = defineConfig({
  testDir: "tests/browser",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  outputDir: "test-results",
  use: {
    baseURL,
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
    video: "off",
  },
  webServer: {
    command:
      ".venv/bin/python manage.py migrate --noinput --settings=config.settings.browser_test && " +
      ".venv/bin/python scripts/prepare_browser_test_database.py && " +
      `.venv/bin/python manage.py runserver 127.0.0.1:${port} --noreload --insecure --settings=config.settings.browser_test`,
    url: `${baseURL}/health/live/`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
