const { test, expect } = require("@playwright/test");

const galleryPath = "/foundation/components/";

async function expectNoPageOverflow(page) {
  const hasPageOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasPageOverflow).toBe(false);
}

test("Django serves the content-free liveness contract", async ({ request }) => {
  const response = await request.get("/health/live/");

  expect(response.status()).toBe(200);
  expect(await response.text()).toBe("OK");
  expect(response.headers()["cache-control"]).toBe("no-store");
});

test("the generic not-found page reveals no requested identifier", async ({ page }) => {
  const failedSubresources = [];
  page.on("response", (response) => {
    if (!response.request().isNavigationRequest() && response.status() >= 400) {
      failedSubresources.push(response.url());
    }
  });
  await page.setViewportSize({ width: 375, height: 812 });
  const response = await page.goto("/synthetic-sensitive-identifier/");

  expect(response.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found (404)");
  await expect(page.locator("body")).toContainText("synthetic-sensitive-identifier");
  await expectNoPageOverflow(page);
  expect(failedSubresources).toEqual([]);
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`component gallery reflows at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(galleryPath);

    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "Interface component gallery",
    );
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("alert")).toBeVisible();
    await expectNoPageOverflow(page);
  });
}

test("keyboard focus is visible and the native dialog restores focus", async ({ page }) => {
  await page.goto(galleryPath);

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const dialogTrigger = page.getByRole("button", { name: "Open sample dialog" });
  await dialogTrigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Confirm sample action" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(":focus")).toHaveCount(1);
  for (let step = 0; step < 4; step += 1) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  }

  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(dialogTrigger).toBeFocused();
});

test("explicit themes persist while system remains the storage-free default", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(galleryPath);

  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");

  await page.getByRole("button", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "light");

  await page.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const storageKeys = await page.evaluate(() => ({
    local: Object.keys(window.localStorage),
    session: Object.keys(window.sessionStorage),
  }));
  expect(storageKeys).toEqual({ local: ["vds-theme"], session: [] });

  await page.getByRole("button", { name: "System" }).click();
  await page.reload();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
  expect(await page.evaluate(() => Object.keys(window.localStorage))).toEqual([]);
});

test("reduced motion and forced colors preserve understandable states", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce", forcedColors: "active" });
  await page.goto(galleryPath);

  const animationDuration = await page
    .locator(".loading-indicator")
    .evaluate((element) => Number.parseFloat(getComputedStyle(element).animationDuration));
  expect(animationDuration).toBeLessThan(0.001);
  await expect(page.getByRole("button", { name: "Save changes" })).toHaveCSS(
    "border-top-color",
    "rgb(0, 0, 0)",
  );
});

test("HTMX and Alpine load locally with sensitive history disabled", async ({ page }) => {
  const externalRequests = [];
  page.on("request", (request) => {
    const requestUrl = new URL(request.url());
    if (requestUrl.hostname !== "127.0.0.1") {
      externalRequests.push(request.url());
    }
  });
  await page.goto(galleryPath);

  const runtime = await page.evaluate(() => ({
    alpine: typeof window.Alpine,
    htmx: typeof window.htmx,
    historyEnabled: window.htmx?.config.historyEnabled,
    historyCacheSize: window.htmx?.config.historyCacheSize,
    allowEval: window.htmx?.config.allowEval,
    allowScriptTags: window.htmx?.config.allowScriptTags,
    includeIndicatorStyles: window.htmx?.config.includeIndicatorStyles,
    selfRequestsOnly: window.htmx?.config.selfRequestsOnly,
  }));
  expect(runtime).toEqual({
    alpine: "object",
    htmx: "object",
    historyEnabled: false,
    historyCacheSize: 0,
    allowEval: false,
    allowScriptTags: false,
    includeIndicatorStyles: false,
    selfRequestsOnly: true,
  });
  expect(externalRequests).toEqual([]);
});

test("the local runtime operates under a strict no-eval CSP", async ({ page }) => {
  const runtimeErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") runtimeErrors.push(message.text());
  });
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await page.route(`**${galleryPath}`, async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      headers: {
        ...response.headers(),
        "content-security-policy":
          "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'",
      },
    });
  });
  await page.goto(galleryPath);

  await expect(page.locator("html")).toHaveClass("js");
  expect(await page.evaluate(() => typeof window.Alpine)).toBe("object");
  expect(await page.evaluate(() => typeof window.htmx)).toBe("object");
  expect(runtimeErrors).toEqual([]);
});

test("the gallery stays usable when JavaScript is disabled", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 375, height: 812 },
  });
  const page = await context.newPage();
  await page.goto(galleryPath);

  await expect(page.locator("html")).toHaveClass("no-js");
  await expect(page.getByLabel("Display name")).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Confirm sample action" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open sample dialog" })).not.toBeVisible();
  await expectNoPageOverflow(page);

  await context.close();
});

test("200 percent zoom retains page-level reflow", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 900 });
  await page.goto(galleryPath);
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByLabel("Display name")).toBeVisible();
  await expectNoPageOverflow(page);
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`login is keyboard-usable at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/login/");

    await expect(page.getByRole("heading", { name: "Administrator sign in" })).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Username")).toBeFocused();
    await expect(page.getByLabel("Username")).toHaveCSS("outline-style", "solid");
    await expectNoPageOverflow(page);
  });
}

test("failed login is generic, clears credentials, focuses the summary, and stores nothing", async ({ page }) => {
  await page.goto("/login/");
  await page.getByLabel("Username").fill("synthetic-unknown-browser-user");
  await page.getByLabel("Password").fill("synthetic-browser-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  const summary = page.locator("[data-error-summary]");
  await expect(summary).toBeFocused();
  await expect(summary).toContainText("Unable to sign in with the credentials provided.");
  await expect(page.getByLabel("Username")).toHaveValue("");
  await expect(page.getByLabel("Password")).toHaveValue("");
  expect(
    await page.evaluate(() => ({
      local: Object.keys(window.localStorage),
      session: Object.keys(window.sessionStorage),
    })),
  ).toEqual({ local: [], session: [] });
});

test("login remains functional without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/login/");
  await page.getByLabel("Username").fill("synthetic-no-script-user");
  await page.getByLabel("Password").fill("synthetic-no-script-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.locator("html")).toHaveClass("no-js");
  await expect(page.getByRole("alert")).toContainText(
    "Unable to sign in with the credentials provided.",
  );
  await expect(page.getByLabel("Username")).toHaveValue("");
  await expectNoPageOverflow(page);
  await context.close();
});

test("the session-expired page is data-free, keyboard-usable, and storage-free", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/session-expired/?next=%2Fdashboard%2F");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Phiên làm việc đã hết hạn");
  const reauthenticationLink = page.getByRole("link", { name: "Đăng nhập lại" });
  await expect(reauthenticationLink).toHaveAttribute("href", "/login/?next=%2Fdashboard%2F");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await expectNoPageOverflow(page);
  expect(
    await page.evaluate(() => ({
      local: Object.keys(window.localStorage),
      session: Object.keys(window.sessionStorage),
    })),
  ).toEqual({ local: [], session: [] });
});

test("the local HTMX expiry handler performs a same-origin full-page redirect", async ({ page }) => {
  await page.goto(galleryPath);

  await page.evaluate(() => {
    const event = new CustomEvent("htmx:beforeSwap", {
      detail: {
        shouldSwap: true,
        xhr: { getResponseHeader: () => "/session-expired/?next=%2Fdashboard%2F" },
      },
    });
    document.dispatchEvent(event);
  });

  await page.waitForURL("**/session-expired/?next=%2Fdashboard%2F");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Phiên làm việc đã hết hạn");
});
