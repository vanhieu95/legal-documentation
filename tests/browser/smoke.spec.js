const { test, expect } = require("@playwright/test");

const galleryPath = "/foundation/components/";
const browserAdministrator = {
  username: "synthetic-browser-administrator",
  password: "synthetic-browser-password-123!",
};

async function signIn(page, credentials = browserAdministrator) {
  await page.goto("/login/");
  await page.getByLabel("Tên đăng nhập").fill(credentials.username);
  await page.getByLabel("Mật khẩu").fill(credentials.password);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
}

async function signInAsAdministrator(page) {
  await signIn(page);
  await expect(page).toHaveURL(/\/dashboard\/$/);
}

async function expectNoPageOverflow(page) {
  const overflow = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    elements: Array.from(document.querySelectorAll("body *"))
      .filter((element) => {
        const bounds = element.getBoundingClientRect();
        return bounds.right > document.documentElement.clientWidth + 1 || bounds.left < -1;
      })
      .slice(0, 10)
      .map((element) => `${element.tagName.toLowerCase()}.${element.className}`),
  }));
  expect(overflow.scrollWidth, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.clientWidth);
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

for (const errorState of [
  { path: "/browser-test/forbidden/", status: 403, heading: "Truy cập bị từ chối" },
  { path: "/browser-test/error/", status: 500, heading: "Lỗi máy chủ" },
]) {
  test(`the live ${errorState.status} page is generic and data-free`, async ({ page }) => {
    const response = await page.goto(errorState.path);

    expect(response.status()).toBe(errorState.status);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(errorState.heading);
    await expect(page.locator("body")).not.toContainText("synthetic-browser-sensitive-detail");
    await expectNoPageOverflow(page);
  });
}

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`component gallery reflows at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(galleryPath);

    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "Bộ sưu tập thành phần giao diện",
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

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`login is keyboard-usable at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/login/");

    await expect(page.getByRole("heading", { name: "Đăng nhập dành cho Quản trị viên" })).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Chuyển đến nội dung chính" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Tên đăng nhập")).toBeFocused();
    await expect(page.getByLabel("Tên đăng nhập")).toHaveCSS("outline-style", "solid");
    await expectNoPageOverflow(page);
  });
}

test("failed login is generic, clears credentials, focuses the summary, and stores nothing", async ({ page }) => {
  await page.goto("/login/");
  await page.getByLabel("Tên đăng nhập").fill("synthetic-unknown-browser-user");
  await page.getByLabel("Mật khẩu").fill("synthetic-browser-password");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();

  const summary = page.locator("[data-error-summary]");
  await expect(summary).toBeFocused();
  await expect(summary).toContainText("Không thể đăng nhập bằng thông tin đã cung cấp.");
  await expect(page.getByLabel("Tên đăng nhập")).toHaveValue("");
  await expect(page.getByLabel("Mật khẩu")).toHaveValue("");
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
  await page.getByLabel("Tên đăng nhập").fill("synthetic-no-script-user");
  await page.getByLabel("Mật khẩu").fill("synthetic-no-script-password");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();

  await expect(page.locator("html")).toHaveClass("no-js");
  await expect(page.getByRole("alert")).toContainText(
    "Không thể đăng nhập bằng thông tin đã cung cấp.",
  );
  await expect(page.getByLabel("Tên đăng nhập")).toHaveValue("");
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
  await expect(page.getByRole("link", { name: "Chuyển đến nội dung chính" })).toBeFocused();
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

test("an Administrator receives the authenticated application shell", async ({ page }) => {
  await signInAsAdministrator(page);

  await expect(page.getByRole("navigation", { name: "Điều hướng chính" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Bảng điều khiển" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("link", { name: "Hồ sơ việc dân sự" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Biểu mẫu" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Nhật ký kiểm tra" })).toBeVisible();
  await expect(page.getByText(browserAdministrator.username)).toBeVisible();
});

test("an active superuser receives the authenticated application shell", async ({ page }) => {
  await signIn(page, {
    username: "synthetic-browser-superuser",
    password: browserAdministrator.password,
  });

  await expect(page).toHaveURL(/\/dashboard\/$/);
  await expect(page.getByRole("link", { name: "Nhật ký kiểm tra" })).toBeVisible();
});

test("a non-Administrator receives only the generic denial", async ({ page }) => {
  await signIn(page, {
    username: "synthetic-browser-non-administrator",
    password: browserAdministrator.password,
  });

  await expect(page).toHaveURL(/\/login\/$/);
  await expect(page.getByRole("alert")).toContainText(
    "Không thể đăng nhập bằng thông tin đã cung cấp.",
  );
  await expect(page.locator("body")).not.toContainText("Administrator");
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`authenticated shell reflows at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);

    await expect(page.getByRole("heading", { name: "Bảng điều khiển" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Đăng xuất" })).toBeVisible();
    await expectNoPageOverflow(page);

    if (viewport.width < 1024) {
      const drawerToggle = page.getByRole("button", { name: "Mở điều hướng" });
      await expect(drawerToggle).toBeVisible();
      const toggleBox = await drawerToggle.boundingBox();
      expect(toggleBox.width).toBeGreaterThanOrEqual(44);
      expect(toggleBox.height).toBeGreaterThanOrEqual(44);
    } else {
      await expect(page.getByRole("button", { name: "Mở điều hướng" })).not.toBeVisible();
    }
  });
}

test("the compact drawer traps focus, closes with Escape, and restores focus", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signInAsAdministrator(page);

  const drawerToggle = page.getByRole("button", { name: "Mở điều hướng" });
  const drawer = page.locator("#primary-navigation");
  await expect(drawer).not.toHaveClass(/is-open/);
  await expect(drawer).toHaveAttribute("inert");
  await expect(page.getByRole("button", { name: "Đóng điều hướng" })).not.toBeVisible();
  await drawerToggle.click();
  await expect(drawer).toHaveClass(/is-open/);
  await expect(drawer).not.toHaveAttribute("inert");
  await expect(page.getByRole("link", { name: "Bảng điều khiển" })).toBeFocused();

  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("link", { name: "Nhật ký kiểm tra" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Bảng điều khiển" })).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(drawer).not.toHaveClass(/is-open/);
  await expect(drawerToggle).toBeFocused();
  await expect(page.locator("body")).not.toHaveClass(/drawer-open/);
});

test("HTMX request events drive the global loading and main busy states", async ({ page }) => {
  await signInAsAdministrator(page);
  const loading = page.locator("#global-loading");
  const main = page.locator("#main-content");

  await page.evaluate(() => document.dispatchEvent(new CustomEvent("htmx:beforeRequest")));
  await expect(loading).toHaveAttribute("aria-busy", "true");
  await expect(loading).toHaveClass(/is-busy/);
  await expect(main).toHaveAttribute("aria-busy", "true");

  await page.evaluate(() => document.dispatchEvent(new CustomEvent("htmx:afterRequest")));
  await expect(loading).toHaveAttribute("aria-busy", "false");
  await expect(loading).not.toHaveClass(/is-busy/);
  await expect(main).toHaveAttribute("aria-busy", "false");
});

test("named shell navigation updates its active state and remains server-protected", async ({ page }) => {
  await signInAsAdministrator(page);
  await page.getByRole("link", { name: "Hồ sơ việc dân sự" }).click();

  await expect(page).toHaveURL(/\/cases\/$/);
  await expect(page.getByRole("link", { name: "Hồ sơ việc dân sự" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("heading", { name: "Hồ sơ việc dân sự" })).toBeVisible();
});

test("the authenticated shell theme stores only an explicit presentation preference", async ({ page }) => {
  await signInAsAdministrator(page);
  await page.getByRole("button", { name: "Tối" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  expect(
    await page.evaluate(() => ({
      local: Object.keys(window.localStorage),
      session: Object.keys(window.sessionStorage),
    })),
  ).toEqual({ local: ["vds-theme"], session: [] });
  expect(await page.evaluate(() => window.localStorage.getItem("vds-theme"))).toBe("dark");
});

test("the authenticated shell operates under a strict local no-eval CSP", async ({ page }) => {
  const runtimeErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") runtimeErrors.push(message.text());
  });
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await page.route("**/dashboard/", async (route) => {
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

  await signInAsAdministrator(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: "Mở điều hướng" }).click();
  await expect(page.locator("#primary-navigation")).toHaveClass(/is-open/);
  expect(runtimeErrors).toEqual([]);
});

test("authenticated navigation and POST logout work without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 375, height: 812 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);

  await expect(page.locator("html")).toHaveClass("no-js");
  await expect(page.getByRole("navigation", { name: "Điều hướng chính" })).toBeVisible();
  await expectNoPageOverflow(page);
  await page.getByRole("button", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL(/\/login\/$/);
  await page.goto("/dashboard/");
  await expect(page).toHaveURL(/\/login\/\?next=(?:%2F|\/)dashboard(?:%2F|\/)$/);

  await context.close();
});

test("the authenticated shell reflows at 200 percent zoom", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 900 });
  await signInAsAdministrator(page);
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });

  await expect(page.getByRole("heading", { name: "Bảng điều khiển" })).toBeVisible();
  await expectNoPageOverflow(page);
});
