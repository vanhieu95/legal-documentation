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

async function createSyntheticCase(page, label) {
  await page.goto("/cases/new/");
  await page.locator('[name="internal_reference"]').fill(`SYN-${label}-${Date.now()}`);
  await page.locator('[name="court"]').selectOption({ label: "SYN-BROWSER — TAND thử nghiệm" });
  await page.locator('[name="matter_type"]').fill("Yêu cầu dân sự ban đầu");
  await page.locator('[name="procedural_stage"]').selectOption("pre_acceptance");
  await page.getByRole("button", { name: "Tạo hồ sơ việc dân sự" }).click();
  await expect(page).toHaveURL(/\/cases\/[0-9a-f-]+\/$/);
  return page.url();
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

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`template upload reflows and supports keyboard navigation at the ${viewport.name} viewport`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);
    await page.goto("/templates/");

    await expect(page.getByRole("heading", { level: 1, name: "Các phiên bản biểu mẫu" })).toBeVisible();
    await expect(page.getByText("SYNTHETIC-DOC", { exact: true })).toBeVisible();
    await expectNoPageOverflow(page);

    const uploadLink = page.getByRole("link", { name: "Tải lên phiên bản mới" });
    await uploadLink.focus();
    await expect(uploadLink).toBeFocused();
    await expect(uploadLink).toHaveCSS("outline-style", "solid");
    await page.keyboard.press("Enter");

    await expect(page.getByRole("heading", { level: 1, name: "Tải lên phiên bản biểu mẫu" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Phiên bản biểu mẫu" })).toBeVisible();
    await expectNoPageOverflow(page);
  });
}

test("template upload announces HTMX errors, preserves safe text, and reports an invalid package", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signInAsAdministrator(page);
  await page.goto("/templates/synthetic-platform-test/upload/");
  const approvalReference = `SYN-BROWSER-UPLOAD-${Date.now()}`;

  await page.getByLabel("Ghi chú hoặc tham chiếu phê duyệt").fill(approvalReference);
  await page.getByRole("textbox", { name: "Phiên bản biểu mẫu" }).fill("!");
  await page.getByLabel("Biểu mẫu DOCX").setInputFiles({
    name: "invalid-form.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("synthetic-invalid-form-docx"),
  });
  await page.getByRole("button", { name: "Tải lên và xác thực" }).click();

  const summary = page.locator("[data-error-summary]");
  await expect(summary).toBeVisible();
  await expect(summary).toBeFocused();
  await expect(page.getByLabel("Ghi chú hoặc tham chiếu phê duyệt")).toHaveValue(
    approvalReference,
  );

  await page.getByRole("textbox", { name: "Phiên bản biểu mẫu" }).fill(`browser-${Date.now()}`);
  await page.getByLabel("Biểu mẫu DOCX").setInputFiles({
    name: "../../unsafe-browser-name.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("synthetic-invalid-docx"),
  });
  let releaseRequest;
  const requestReleased = new Promise((resolve) => {
    releaseRequest = resolve;
  });
  let observeRequest;
  const requestObserved = new Promise((resolve) => {
    observeRequest = resolve;
  });
  await page.route("**/templates/synthetic-platform-test/upload/", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    observeRequest();
    await requestReleased;
    await route.continue();
  });
  const submission = page.getByRole("button", { name: "Tải lên và xác thực" }).click();
  await requestObserved;
  await expect(page.locator("#template-upload-workflow")).toHaveAttribute("aria-busy", "true");
  await expect(page.locator("#template-upload-busy")).toBeVisible();
  releaseRequest();
  await submission;

  const result = page.locator("[data-template-result]");
  await expect(result).toBeVisible();
  await expect(result).toBeFocused();
  await expect(result).toContainText("Xác thực tự động không đạt yêu cầu");
  await expect(result).toContainText("Tệp không phải là gói DOCX có thể đọc.");
  await expect(page.locator("body")).not.toContainText("unsafe-browser-name.docx");
  await expectNoPageOverflow(page);
});

test("template upload remains usable without JavaScript at 200 percent zoom", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 640, height: 900 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  await page.goto("/templates/synthetic-platform-test/upload/");
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  await page.getByRole("textbox", { name: "Phiên bản biểu mẫu" }).fill("!");
  await page.getByLabel("Ghi chú hoặc tham chiếu phê duyệt").fill("SYN-BROWSER-NOJS");
  await page.getByLabel("Biểu mẫu DOCX").setInputFiles({
    name: "invalid-nojs-form.docx",
    mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    buffer: Buffer.from("synthetic-invalid-nojs-form-docx"),
  });
  await page.getByRole("button", { name: "Tải lên và xác thực" }).click();

  await expect(page.locator("html")).toHaveClass("no-js");
  await expect(page.getByLabel("Ghi chú hoặc tham chiếu phê duyệt")).toHaveValue(
    "SYN-BROWSER-NOJS",
  );
  await expect(page.locator("[data-error-summary]")).toBeVisible();
  await expectNoPageOverflow(page);
  await context.close();
});

test("template activation confirmation traps focus and activates through HTMX", async ({ page }) => {
  await signInAsAdministrator(page);
  await page.goto("/templates/");
  const activationLink = page.getByRole("link", { name: "Kích hoạt" }).first();
  await activationLink.focus();
  await activationLink.press("Enter");

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("heading", { name: "Kích hoạt phiên bản biểu mẫu" })).toBeVisible();
  const confirmButton = page.getByRole("button", { name: "Xác nhận kích hoạt" });
  await expect(confirmButton).toBeFocused();
  const activationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/activate/") && response.request().method() === "POST",
  );
  await confirmButton.click();
  expect((await activationResponse).status()).toBe(204);

  await expect(page).toHaveURL(/\/templates\/$/);
  await expect(page.getByRole("link", { name: "Ngừng sử dụng" }).first()).toBeVisible();
});

test("template activation has a JavaScript-disabled confirmation fallback", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  await page.goto("/templates/");
  await page.getByRole("link", { name: "Kích hoạt" }).first().click();

  await expect(page).toHaveURL(/\/activate\/$/);
  await expect(page.getByRole("heading", { name: "Kích hoạt phiên bản biểu mẫu" })).toBeVisible();
  await page.getByRole("button", { name: "Xác nhận kích hoạt" }).click();
  await expect(page).toHaveURL(/\/templates\/$/);
  await context.close();
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`document draft framework reflows at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);
    const caseUrl = await createSyntheticCase(page, `DOCUMENT-${viewport.name}`);
    const selectorUrl = `${new URL(caseUrl).pathname}documents/`;
    await page.goto(selectorUrl);

    await expect(page.getByRole("heading", { level: 1, name: "Chọn tài liệu" })).toBeVisible();
    const openForm = page.getByRole("link", { name: "Mở biểu mẫu tài liệu" });
    await openForm.focus();
    await expect(openForm).toBeFocused();
    await openForm.press("Enter");
    await expect(page.getByRole("heading", { name: "Giá trị riêng của tài liệu" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Giá trị dùng chung từ hồ sơ" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ghi đè của quản trị viên" })).toBeVisible();
    await expectNoPageOverflow(page);

    await page.getByRole("button", { name: "Lưu bản nháp" }).click();
    const summary = page.locator("[data-error-summary]");
    await expect(summary).toBeVisible();
    await expect(summary).toBeFocused();
  });
}

test("document draft works without JavaScript at 200 percent zoom", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 640, height: 900 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  const caseUrl = await createSyntheticCase(page, "DOCUMENT-NOJS");
  await page.goto(`${new URL(caseUrl).pathname}documents/`);
  await page.getByRole("link", { name: "Mở biểu mẫu tài liệu" }).click();
  await page.locator('[name="title"]').fill("Bản nháp thử nghiệm");
  await page.getByRole("button", { name: "Lưu bản nháp" }).click();

  await expect(page).toHaveURL(/\/documents\/synthetic-platform-test\/$/);
  await expect(page.locator('[name="title"]')).toHaveValue("Bản nháp thử nghiệm");
  await expect(page.locator("html")).toHaveClass("no-js");
  await expectNoPageOverflow(page);
  await context.close();
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`case dashboard reflows at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);

    await expect(page.getByRole("heading", { level: 1, name: "Bảng điều khiển" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Xem \d+ hồ sơ đang hoạt động/ })).toHaveAttribute(
      "href",
      "/cases/?archive_state=active",
    );
    await expect(page.getByRole("link", { name: /Xem \d+ hồ sơ đã lưu trữ/ })).toHaveAttribute(
      "href",
      "/cases/?archive_state=archived",
    );
    await expect(page.getByRole("heading", { name: "Hoạt động hồ sơ gần đây" })).toBeVisible();
    await expect(page.getByText("Chức năng tài liệu chưa khả dụng")).toBeVisible();
    await expectNoPageOverflow(page);

    const activeCard = page.getByRole("link", { name: /Xem \d+ hồ sơ đang hoạt động/ });
    await activeCard.focus();
    await expect(activeCard).toBeFocused();
    await expect(activeCard).toHaveCSS("outline-style", "solid");
  });
}

test("dashboard case activity refreshes as a narrow HTMX fragment", async ({ page }) => {
  await signInAsAdministrator(page);
  let releaseRequest;
  const requestReleased = new Promise((resolve) => {
    releaseRequest = resolve;
  });
  let observeRequest;
  const requestObserved = new Promise((resolve) => {
    observeRequest = resolve;
  });
  await page.route("**/dashboard/", async (route) => {
    observeRequest();
    await requestReleased;
    await route.continue();
  });
  const fragmentResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/dashboard/") &&
      response.request().headers()["hx-request"] === "true",
  );
  const click = page.getByRole("link", { name: "Làm mới hoạt động hồ sơ" }).click();
  await requestObserved;
  await expect(page.locator("#dashboard-case-activity")).toHaveAttribute("aria-busy", "true");
  await expect(page.locator("#dashboard-case-activity-loading")).toBeVisible();
  releaseRequest();
  await click;
  const response = await fragmentResponse;

  expect(response.status()).toBe(200);
  expect(response.headers().vary).toContain("HX-Request");
  await expect(page.locator("#dashboard-case-activity")).toHaveCount(1);
  await expect(page.locator("#dashboard-case-activity")).toHaveAttribute("aria-busy", "false");
  await expect(page).toHaveURL(/\/dashboard\/$/);
  const browserStorage = await page.evaluate(() => ({
    local: { ...window.localStorage },
    session: { ...window.sessionStorage },
  }));
  expect(browserStorage.session).toEqual({});
  expect(JSON.stringify(browserStorage)).not.toContain("SYN-");
});

test("dashboard announces a case-activity network error without exposing case data", async ({ page }) => {
  await signInAsAdministrator(page);
  await page.route("**/dashboard/", (route) => route.abort("failed"));

  await page.getByRole("link", { name: "Làm mới hoạt động hồ sơ" }).click();

  await expect(page.locator("#global-error")).toHaveText(
    "Không thể làm mới hoạt động hồ sơ. Kiểm tra kết nối rồi thử lại.",
  );
  await expect(page.locator("#dashboard-case-activity")).toHaveAttribute("aria-busy", "false");
});

test("dashboard recent activity opens the authorized case detail", async ({ page }) => {
  await signInAsAdministrator(page);
  const detailUrl = await createSyntheticCase(page, "DASHBOARD-ACTIVITY");
  const reference = await page.getByRole("heading", { level: 1 }).textContent();
  await page.goto("/dashboard/");

  const activityItem = page.locator(".dashboard-activity-list li").filter({ hasText: reference });
  await expect(activityItem).toContainText("Hồ sơ đã được cập nhật");
  await expect(activityItem.getByRole("link", { name: reference, exact: true })).toHaveAttribute(
    "href",
    new URL(detailUrl).pathname,
  );
});

test("dashboard case links work without JavaScript and store no case state", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 375, height: 812 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);

  await page.getByRole("link", { name: /Xem \d+ hồ sơ đang hoạt động/ }).click();

  await expect(page).toHaveURL(/\/cases\/\?archive_state=active$/);
  await expect(page.locator('select[name="archive_state"]')).toHaveValue("active");
  await expectNoPageOverflow(page);
  await context.close();
});

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
    historyEnabled: true,
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
  await expect(page.getByRole("link", { name: "Hồ sơ việc dân sự", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("heading", { name: "Hồ sơ việc dân sự" })).toBeVisible();
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`case creation and overview reflow at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);
    await page.goto("/cases/new/");

    await page.locator('[name="internal_reference"]').fill(`SYN-BROWSER-${viewport.name}-${Date.now()}`);
    await page.locator('[name="court"]').selectOption({ label: "SYN-BROWSER — TAND thử nghiệm" });
    await page.locator('[name="matter_type"]').fill("Yêu cầu dân sự Unicode thử nghiệm");
    await page.locator('[name="procedural_stage"]').selectOption("pre_acceptance");
    await expectNoPageOverflow(page);
    await page.getByRole("button", { name: "Tạo hồ sơ việc dân sự" }).click();

    await expect(page).toHaveURL(/\/cases\/[0-9a-f-]+\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("SYN-BROWSER-");
    await expect(page.getByText("Yêu cầu dân sự Unicode thử nghiệm")).toBeVisible();
    await expectNoPageOverflow(page);
  });
}

test("invalid HTMX case creation preserves input and focuses its linked summary", async ({ page }) => {
  await signInAsAdministrator(page);
  await page.goto("/cases/new/");
  await page.locator('[name="internal_reference"]').fill(`SYN-BROWSER-INVALID-${Date.now()}`);
  await page.locator('[name="court"]').selectOption({ label: "SYN-BROWSER — TAND thử nghiệm" });
  await page.locator('[name="matter_type"]').fill("Giá trị Unicode cần giữ lại");
  await page.locator('[name="procedural_stage"]').selectOption("accepted");
  await page.locator('[name="acceptance_number"]').fill("42");
  await page.getByRole("button", { name: "Tạo hồ sơ việc dân sự" }).click();

  const summary = page.locator("[data-error-summary]");
  await expect(summary).toBeFocused();
  await expect(summary.getByRole("link").first()).toBeVisible();
  await expect(page.locator('[name="matter_type"]')).toHaveValue("Giá trị Unicode cần giữ lại");
  expect(
    await page.evaluate(() => ({
      local: Object.keys(window.localStorage),
      session: Object.keys(window.sessionStorage),
    })),
  ).toEqual({ local: [], session: [] });
});

test("case creation reflows at 200 percent zoom with visible keyboard focus", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 900 });
  await signInAsAdministrator(page);
  await page.goto("/cases/new/");
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });

  const referenceField = page.locator('[name="internal_reference"]');
  await referenceField.focus();
  await expect(referenceField).toBeFocused();
  await expect(referenceField).toHaveCSS("outline-style", "solid");
  await expectNoPageOverflow(page);
});

test("case creation and detail remain usable without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  await page.goto("/cases/new/");
  await page.locator('[name="internal_reference"]').fill(`SYN-BROWSER-NOJS-${Date.now()}`);
  await page.locator('[name="court"]').selectOption({ label: "SYN-BROWSER — TAND thử nghiệm" });
  await page.locator('[name="matter_type"]').fill("Yêu cầu không JavaScript");
  await page.locator('[name="procedural_stage"]').selectOption("pre_acceptance");
  await page.getByRole("button", { name: "Tạo hồ sơ việc dân sự" }).click();

  await expect(page).toHaveURL(/\/cases\/[0-9a-f-]+\/$/);
  await expect(page.locator("html")).toHaveClass("no-js");
  await expect(page.getByText("Yêu cầu không JavaScript")).toBeVisible();
  await expectNoPageOverflow(page);
  await context.close();
});

test("case-list search is debounced, cancels obsolete work, and restores URL history", async ({
  page,
}) => {
  await signInAsAdministrator(page);
  await createSyntheticCase(page, "LIST-HISTORY");
  await page.goto("/cases/");
  const search = page.getByLabel("Tìm kiếm", { exact: true });
  const observedQueries = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/cases/" && url.searchParams.has("q")) {
      observedQueries.push(url.searchParams.get("q"));
    }
  });

  await search.pressSequentially("SYN-LIST-HISTORY", { delay: 25 });
  await expect(page).toHaveURL(/q=SYN-LIST-HISTORY/);
  await expect(page.getByRole("link", { name: "Xem hồ sơ" }).first()).toBeVisible();
  expect(observedQueries.length).toBeLessThanOrEqual(2);
  expect(observedQueries.at(-1)).toBe("SYN-LIST-HISTORY");
  await expect(page.locator("#case-results")).toHaveAttribute("aria-busy", "false");

  await search.fill("SYN-NO-BROWSER-MATCH");
  await expect(page).toHaveURL(/q=SYN-NO-BROWSER-MATCH/);
  await expect(page.getByRole("heading", { name: "Không có hồ sơ nào khớp" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/q=SYN-LIST-HISTORY/);
  await page.goForward();
  await expect(page).toHaveURL(/q=SYN-NO-BROWSER-MATCH/);
  await page.reload();
  await expect(search).toHaveValue("SYN-NO-BROWSER-MATCH");
  expect(await page.evaluate(() => Object.keys(window.sessionStorage))).toEqual([]);
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`case list keeps identifiers, status, actions, and keyboard sorting at the ${viewport.name} viewport`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);
    await createSyntheticCase(page, `LIST-${viewport.name}`);
    await page.goto("/cases/?sort=court&page_size=10");

    await expect(page.getByRole("heading", { level: 1, name: "Hồ sơ việc dân sự" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Xem hồ sơ" }).first()).toBeVisible();
    await expect(page.locator("[data-case-id]").first().getByText("Đang hoạt động")).toBeVisible();
    if (viewport.name === "compact") {
      const sortControl = page.getByLabel("Thứ tự sắp xếp");
      await sortControl.focus();
      await expect(sortControl).toBeFocused();
      await sortControl.selectOption("-court");
    } else {
      const courtSort = page.getByRole("link", { name: "Tòa án", exact: true }).last();
      await courtSort.focus();
      await expect(courtSort).toBeFocused();
      await page.keyboard.press("Enter");
    }
    await expect(page).toHaveURL(/sort=-court/);
    if (viewport.name === "compact") {
      await page.evaluate(() => {
        document.documentElement.style.zoom = "2";
      });
    }
    await expectNoPageOverflow(page);
  });
}

test("case-list filtering and ordinary links work without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 640, height: 900 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  await page.goto("/cases/");
  await page.getByLabel("Tìm kiếm", { exact: true }).fill("SYN-BROWSER");
  await page.getByRole("button", { name: "Áp dụng bộ lọc" }).click();

  await expect(page).toHaveURL(/q=SYN-BROWSER/);
  await expect(page.locator("html")).toHaveClass("no-js");
  await page.getByRole("link", { name: "Xem hồ sơ" }).first().click();
  await expect(page).toHaveURL(/\/cases\/[0-9a-f-]+\/$/);
  await expectNoPageOverflow(page);
  await context.close();
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`case sections use canonical HTMX navigation at the ${viewport.name} viewport`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);
    const detailUrl = await createSyntheticCase(page, `SECTIONS-${viewport.name}`);
    const participants = page.locator('a[href$="?section=participants"]');
    await participants.focus();
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(`${detailUrl}?section=participants`);
    await expect(page.locator("#case-section-heading")).toBeFocused();
    await expect(page.getByText("Chưa có người tham gia tố tụng")).toBeVisible();
    if (viewport.name === "compact") {
      await page.evaluate(() => {
        document.documentElement.style.zoom = "2";
      });
    }
    await expectNoPageOverflow(page);
  });
}

test("relationship formsets add, remove, validate, announce success, and preserve conflicts", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signInAsAdministrator(page);
  const detailUrl = await createSyntheticCase(page, "RELATIONSHIPS");
  await page.goto(`${detailUrl}?section=participants`);
  await page.locator('a[href*="/relationships/participants/"]').click();
  await expect(page).toHaveURL(/\/relationships\/participants\/$/);

  const addButton = page.locator("[data-formset-add]");
  await addButton.click();
  await expect(page.locator('[name="participants-1-entity"]')).toBeFocused();
  await page.locator('[data-formset-row]').last().locator("[data-formset-remove]").click();
  await expect(addButton).toBeFocused();

  await page.locator('[name="participants-0-role"]').selectOption("requester");
  await page.locator('[name="participants-0-ordering"]').fill("0");
  await page.getByRole("button", { name: "Lưu quan hệ" }).click();
  await expect(page.locator("[data-error-summary]")).toBeFocused();

  await page.locator('[name="participants-0-entity"]').selectOption({
    label: "Người tham gia thử nghiệm",
  });
  const secondTab = await page.context().newPage();
  await secondTab.goto(page.url());
  await page.getByRole("button", { name: "Lưu quan hệ" }).click();
  const success = page.locator("#relationship-form .alert-success");
  await expect(success).toBeFocused();

  await secondTab.locator('[name="participants-0-entity"]').selectOption({
    label: "Người tham gia thử nghiệm",
  });
  await secondTab.locator('[name="participants-0-role"]').selectOption("witness");
  await secondTab.locator('[name="participants-0-ordering"]').fill("1");
  await secondTab.getByRole("button", { name: "Lưu quan hệ" }).click();
  await expect(secondTab.locator("[data-conflict-summary]")).toBeFocused();
  await expect(secondTab.locator('[name="participants-0-role"]')).toHaveValue("witness");
  await secondTab.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  await expectNoPageOverflow(secondTab);
  await secondTab.getByRole("link", { name: "Tải lại quan hệ hiện tại" }).click();
  await expect(secondTab.locator('[name="expected_revision"]')).toHaveValue("2");
  await secondTab.close();
});

test("case section navigation and relationship submission work without JavaScript", async ({
  browser,
}) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 375, height: 812 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  const detailUrl = await createSyntheticCase(page, "RELATIONSHIPS-NOJS");
  await page.locator('a[href$="?section=participants"]').click();
  await expect(page).toHaveURL(`${detailUrl}?section=participants`);
  await page.locator('a[href*="/relationships/participants/"]').click();
  await page.locator('[name="participants-0-entity"]').selectOption({
    label: "Người tham gia thử nghiệm",
  });
  await page.locator('[name="participants-0-role"]').selectOption("requester");
  await page.locator('[name="participants-0-ordering"]').fill("0");
  await page.getByRole("button", { name: "Lưu quan hệ" }).click();

  await expect(page).toHaveURL(/\?section=participants$/);
  await expect(page.locator("html")).toHaveClass("no-js");
  await expect(page.getByText("Người tham gia thử nghiệm trình duyệt")).toBeVisible();
  await expectNoPageOverflow(page);
  await context.close();
});

test("two enhanced tabs recover safely from an optimistic case-edit conflict", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signInAsAdministrator(page);
  const detailUrl = await createSyntheticCase(page, "BROWSER-CONFLICT");
  const editUrl = `${detailUrl}edit/`;
  const secondTab = await page.context().newPage();
  await Promise.all([page.goto(editUrl), secondTab.goto(editUrl)]);
  await expect(page.locator('[name="expected_revision"]')).toHaveValue("1");
  await expect(secondTab.locator('[name="expected_revision"]')).toHaveValue("1");

  await page.locator('[name="matter_type"]').fill("Giá trị đã lưu từ tab thứ nhất");
  await secondTab.locator('[name="matter_type"]').fill("Giá trị đang chờ từ tab thứ hai");
  await page.getByRole("button", { name: "Lưu hồ sơ" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(detailUrl);
  await secondTab.getByRole("button", { name: "Lưu hồ sơ" }).click();

  const conflict = secondTab.locator("[data-conflict-summary]");
  await expect(conflict).toBeFocused();
  await expect(secondTab.locator('[name="matter_type"]')).toHaveValue(
    "Giá trị đang chờ từ tab thứ hai",
  );
  await expect(secondTab.locator('[name="expected_revision"]')).toHaveValue("1");
  await expectNoPageOverflow(secondTab);
  await secondTab.getByRole("link", { name: "Tải lại hồ sơ mới nhất" }).click();
  await expect(secondTab.locator('[name="matter_type"]')).toHaveValue(
    "Giá trị đã lưu từ tab thứ nhất",
  );
  await expect(secondTab.locator('[name="expected_revision"]')).toHaveValue("2");
  await secondTab.close();
});

test("case editing and full-page conflict recovery work without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 1440, height: 900 },
  });
  const firstTab = await context.newPage();
  await signInAsAdministrator(firstTab);
  const detailUrl = await createSyntheticCase(firstTab, "BROWSER-NOJS-EDIT");
  const editUrl = `${detailUrl}edit/`;
  const secondTab = await context.newPage();
  await Promise.all([firstTab.goto(editUrl), secondTab.goto(editUrl)]);

  await firstTab.locator('[name="matter_type"]').fill("Giá trị không JavaScript đã lưu");
  await secondTab.locator('[name="matter_type"]').fill("Giá trị không JavaScript bị xung đột");
  await firstTab.getByRole("button", { name: "Lưu hồ sơ" }).click();
  await expect(firstTab).toHaveURL(detailUrl);
  const conflictResponse = await Promise.all([
    secondTab.waitForNavigation(),
    secondTab.getByRole("button", { name: "Lưu hồ sơ" }).click(),
  ]);

  expect(conflictResponse[0].status()).toBe(409);
  await expect(secondTab.locator("html")).toHaveClass("no-js");
  await expect(secondTab.locator("[data-conflict-summary]")).toBeVisible();
  await expect(secondTab.locator('[name="matter_type"]')).toHaveValue(
    "Giá trị không JavaScript bị xung đột",
  );
  await secondTab.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  await expectNoPageOverflow(secondTab);
  await context.close();
});

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`archive confirmation traps focus, cancels safely, restores focus, and completes at the ${viewport.name} viewport`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);
    const detailUrl = await createSyntheticCase(page, `BROWSER-ARCHIVE-${viewport.name}`);
    const trigger = page.getByRole("link", { name: "Lưu trữ hồ sơ" });
    await trigger.focus();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("dialog", { name: "Lưu trữ hồ sơ" });
    await expect(dialog).toBeVisible();
    await expect(page.getByLabel("Lý do lưu trữ")).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.getByRole("button", { name: "Hủy" })).toBeFocused();
    await dialog.getByRole("button", { name: "Hủy" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();

    await trigger.click();
    await expect(dialog).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();

    await trigger.click();
    await expect(dialog).toBeVisible();
    await page.getByLabel("Lý do lưu trữ").fill("Lý do lưu trữ Unicode thử nghiệm");
    await dialog.getByRole("button", { name: "Xác nhận lưu trữ" }).click();
    await expect(page).toHaveURL(detailUrl);
    await expect(page.getByRole("link", { name: "Khôi phục hồ sơ" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Chỉnh sửa hồ sơ" })).not.toBeVisible();
    await expectNoPageOverflow(page);
  });
}

test("archive and restore confirmations work without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 375, height: 812 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  const detailUrl = await createSyntheticCase(page, "BROWSER-NOJS-ARCHIVE");

  await page.getByRole("link", { name: "Lưu trữ hồ sơ" }).click();
  await expect(page.locator("html")).toHaveClass("no-js");
  await page.getByLabel("Lý do lưu trữ").fill("Lý do không JavaScript");
  await page.getByRole("button", { name: "Xác nhận lưu trữ" }).click();
  await expect(page).toHaveURL(detailUrl);
  await page.getByRole("link", { name: "Khôi phục hồ sơ" }).click();
  await page.getByRole("button", { name: "Xác nhận khôi phục" }).click();
  await expect(page).toHaveURL(detailUrl);
  await expect(page.getByRole("link", { name: "Chỉnh sửa hồ sơ" })).toBeVisible();
  await expectNoPageOverflow(page);
  await context.close();
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

for (const viewport of [
  { name: "compact", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "wide", width: 1440, height: 900 },
]) {
  test(`court references reflow at the ${viewport.name} viewport`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await signInAsAdministrator(page);
    await page.goto("/case-references/courts/");

    await expect(page.getByRole("heading", { level: 1, name: "Tòa án" })).toBeVisible();
    if (viewport.width < 640) {
      await expect(page.locator(".reference-card-view")).toBeVisible();
      await expect(page.locator(".reference-card-view")).toContainText(
        "Tòa án nhân dân thử nghiệm trình duyệt",
      );
      await expect(page.locator(".reference-table-view")).not.toBeVisible();
    } else {
      await expect(page.locator(".reference-table-view")).toBeVisible();
      await expect(page.locator(".reference-table-view")).toContainText(
        "Tòa án nhân dân thử nghiệm trình duyệt",
      );
      await expect(page.locator(".reference-card-view")).not.toBeVisible();
    }
    await expectNoPageOverflow(page);
  });
}

test("an invalid HTMX reference form swaps the 422 fragment and focuses its summary", async ({
  page,
}) => {
  await signInAsAdministrator(page);
  await page.goto("/case-references/courts/");
  await page.getByRole("link", { name: "Tạo dữ liệu tham chiếu" }).click();
  await expect(page.getByRole("heading", { name: "Tạo Tòa án" })).toBeFocused();

  await page.locator("#id_code").fill(" ");
  await page.locator("#id_full_name").fill("Tòa án thử nghiệm đã nhập");
  await page.locator("#id_short_name").fill("TAND thử nghiệm");
  await page.locator("#id_level").selectOption("district");
  await page.locator("#id_address").fill("Địa chỉ hành chính thử nghiệm");
  await page.getByRole("button", { name: "Lưu dữ liệu tham chiếu" }).click();

  const summary = page.locator("[data-error-summary]");
  await expect(summary).toBeVisible();
  await expect(summary).toBeFocused();
  await expect(page.locator("#id_full_name")).toHaveValue("Tòa án thử nghiệm đã nhập");
  await expect(page.locator("#reference-form")).toBeVisible();
});

test("the enhanced deactivation confirmation names the court and restores focus", async ({
  page,
}) => {
  await signInAsAdministrator(page);
  await page.goto("/case-references/courts/");
  const trigger = page.getByRole("link", { name: "Ngừng sử dụng" }).first();
  await trigger.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("SYN-BROWSER");
  await expect(dialog.getByRole("button", { name: "Xác nhận ngừng sử dụng" })).toBeFocused();
  await dialog.getByRole("button", { name: "Hủy" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
});

test("reference editing works without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 375, height: 812 },
  });
  const page = await context.newPage();
  await signInAsAdministrator(page);
  await page.goto("/case-references/courts/?q=SYN-BROWSER");
  await page.getByRole("link", { name: "Chỉnh sửa" }).first().click();

  await page.locator("#id_short_name").fill("TAND không JavaScript");
  await page.getByRole("button", { name: "Lưu dữ liệu tham chiếu" }).click();

  await expect(page).toHaveURL(/\/case-references\/courts\/.+\/edit\/$/);
  await expect(page.locator(".alert-success")).toContainText("Đã cập nhật dữ liệu tham chiếu");
  await expect(page.locator("#id_short_name")).toHaveValue("TAND không JavaScript");
  await expectNoPageOverflow(page);
  await context.close();
});
