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
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Không tìm thấy");
  await expect(page.locator("body")).not.toContainText("synthetic-sensitive-identifier");
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
      "Thư viện thành phần giao diện",
    );
    await expect(page.getByRole("table")).toBeVisible();
    await expect(page.getByRole("alert")).toBeVisible();
    await expectNoPageOverflow(page);
  });
}

test("keyboard focus is visible and the native dialog restores focus", async ({ page }) => {
  await page.goto(galleryPath);

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Chuyển đến nội dung chính" });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const dialogTrigger = page.getByRole("button", { name: "Mở hộp thoại mẫu" });
  await dialogTrigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Xác nhận thao tác mẫu" });
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

  await page.getByRole("button", { name: "Sáng" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "light");

  await page.getByRole("button", { name: "Tối" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const storageKeys = await page.evaluate(() => ({
    local: Object.keys(window.localStorage),
    session: Object.keys(window.sessionStorage),
  }));
  expect(storageKeys).toEqual({ local: ["vds-theme"], session: [] });

  await page.getByRole("button", { name: "Hệ thống" }).click();
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
  await expect(page.getByRole("button", { name: "Lưu thay đổi" })).toHaveCSS(
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
  await expect(page.getByLabel("Tên hiển thị")).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Xác nhận thao tác mẫu" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Mở hộp thoại mẫu" })).not.toBeVisible();
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
  await expect(page.getByLabel("Tên hiển thị")).toBeVisible();
  await expectNoPageOverflow(page);
});
