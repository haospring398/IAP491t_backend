import { test, expect, type Page, type Route } from "@playwright/test";
import { policy } from "../../lib/contracts";
const fixture = (name = "fixture.eml") => ({ name, mimeType: "message/rfc822", buffer: Buffer.from("From: fixture@example.test\r\nSubject: Test fixture\r\n\r\nExample body") });
async function respond(route: Route, body: unknown, status = 200) {
  const id = route.request().headers()["x-request-id"];
  await route.fulfill({ status, contentType: "application/json", headers: { "X-Request-ID": id }, body: JSON.stringify(body) });
}
async function select(page: Page, name = "fixture.eml") { await page.locator("#email-file").setInputFiles(fixture(name)); }
async function drop(page: Page, names: string[]) {
  await page.locator(".drop-zone").evaluate((element, filenames) => {
    const transfer = new DataTransfer();
    for (const filename of filenames) transfer.items.add(new File(["Subject: Fixture\r\n\r\nBody"], filename, { type: "message/rfc822" }));
    element.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, names);
}
test.beforeEach(async ({ page }) => {
  // Mark every intercepted response as test-only sample evidence; production has no fixture switch.
  await page.addInitScript(() => document.addEventListener("DOMContentLoaded", () => {
    const note = document.createElement("p"); note.textContent = "Sample result — not a real analysis"; note.dataset.testid = "fixture-note"; document.body.prepend(note);
  }));
  await page.route("**/api/analysis-status?*", route => route.fulfill({ status: 503, contentType: "text/html", body: "fixture status unavailable" }));
  await page.goto("/");
});
test("initial/select/change/remove/refresh, picker cancellation, both neutral labels and no automatic upload", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/analyze", async route => { requests++; await respond(route, { analysis_status: "completed", label: requests === 1 ? "legit" : "phishing" }); });
  const analyze = page.getByRole("button", { name: "Analyze", exact: true });
  await expect(analyze).toBeDisabled(); await expect(page.getByText("No file selected.")).toBeVisible();
  await select(page, "first.EML"); await expect(analyze).toBeEnabled(); expect(requests).toBe(0);
  await page.locator("#email-file").setInputFiles([]); await expect(page.getByText("first.EML", { exact: true })).toBeVisible();
  await analyze.click(); await expect(page.getByText("Result: Legit", { exact: true })).toBeVisible();
  await select(page, "second.eml"); await expect(page.getByText("Result: Legit")).toHaveCount(0); await analyze.click();
  await expect(page.getByText("Result: Phishing", { exact: true })).toBeVisible();
  await expect(page.locator(".status-result-area .filename")).toHaveText("second.eml");
  await page.getByRole("button", { name: "Remove file" }).click(); await expect(page.getByText("No file selected.")).toBeVisible();
  await select(page); await page.reload(); await expect(analyze).toBeDisabled();
  await expect(page.getByRole("navigation")).toHaveCount(0); await expect(page.getByRole("link")).toHaveCount(0);
});
test("mixed-positive demo label and visible accuracy disclosure", async ({ page }) => {
  await page.route("**/api/analyze", route => respond(route, { analysis_status: "completed", label: "spam_or_phishing" }));
  await expect(page.getByRole("note")).toHaveText("Local demo model: phishing detection accuracy has not been independently established.");
  await select(page, "mixed-positive.eml");
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await expect(page.getByText("Result: Spam / phishing", { exact: true })).toBeVisible();
  await expect(page.locator(".status-result-area .filename")).toHaveText("mixed-positive.eml");
});
test("explanation lists catalogued factors in text with neutral bars and clears with the result", async ({ page }) => {
  let requests = 0;
  const explanation = { factors: [{ factor: "num_attachments", direction: "positive", strength: 1 }, { factor: "text_content", direction: "negative", strength: 0.4 }, { factor: "num_urls", direction: "positive", strength: 0.12 }] };
  await page.route("**/api/analyze", route => { requests++; return requests === 1 ? respond(route, { analysis_status: "completed", label: "phishing", explanation })
    : respond(route, { analysis_status: "completed", label: "legit", explanation: { factors: [{ factor: "unknown_feature", direction: "positive", strength: 1 }] } }); });
  await select(page, "explained.eml"); await page.getByRole("button", { name: "Analyze", exact: true }).click();
  const list = page.locator(".explanation-list");
  await expect(list.getByRole("heading", { name: "What the model relied on" })).toBeVisible();
  await expect(list).toContainText("They are not proof that the email is safe or malicious.");
  const items = list.locator("li"); await expect(items).toHaveCount(3);
  await expect(items.nth(0)).toContainText("Number of attachments (Known dataset bias)"); await expect(items.nth(0)).toContainText("Toward Phishing · Strong");
  await expect(items.nth(1)).toContainText("Overall wording (text model)"); await expect(items.nth(1)).toContainText("Toward Legit · Moderate");
  await expect(items.nth(2)).toContainText("Number of links"); await expect(items.nth(2)).toContainText("Toward Phishing · Weak");
  await expect(list.locator(".factor-bar").first()).toHaveAttribute("aria-hidden", "true");
  const fills = await list.locator(".factor-bar > span").evaluateAll(spans => spans.map(span => getComputedStyle(span).backgroundColor));
  expect(new Set(fills).size).toBe(1);
  await expect(page.getByRole("status")).not.toContainText("What the model relied on");
  await page.getByRole("button", { name: "Remove file" }).click(); await expect(list).toHaveCount(0);
  await select(page, "unknown-factor.eml"); await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await expect(page.getByLabel("Analysis status").getByRole("alert")).toBeVisible();
  await expect(page.locator(".result-label")).toHaveCount(0); await expect(list).toHaveCount(0);
});
test("drop validation rejects multiple and invalid replacements and clears old result", async ({ page }) => {
  await page.route("**/api/analyze", route => respond(route, { analysis_status: "completed", label: "legit" }));
  await drop(page, ["valid.eml"]); await page.getByRole("button", { name: "Analyze", exact: true }).click(); await expect(page.getByText("Result: Legit")).toBeVisible();
  await drop(page, ["one.eml", "two.eml"]); await expect(page.getByLabel("Analysis status").getByRole("alert")).toContainText("Choose one .eml file."); await expect(page.getByText("Result: Legit")).toHaveCount(0);
  await select(page); await page.locator("#email-file").setInputFiles({ name: "bad.txt", mimeType: "text/plain", buffer: Buffer.from("x") }); await expect(page.getByLabel("Analysis status").getByRole("alert")).toBeVisible();
  await page.locator("#email-file").setInputFiles({ name: "empty.eml", mimeType: "message/rfc822", buffer: Buffer.alloc(0) }); await expect(page.getByLabel("Analysis status").getByRole("alert")).toContainText("This file is empty.");
  await page.locator("#email-file").setInputFiles({ name: "big.eml", mimeType: "message/rfc822", buffer: Buffer.alloc(policy.limits.fileBytes + 1) }); await expect(page.getByLabel("Analysis status").getByRole("alert")).toContainText("2 MiB limit");
});
test("active attempt locks mutation and duplicate starts; status failure leaves terminal POST authoritative", async ({ page }) => {
  let requests = 0; let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/analyze", async route => { requests++; await pending; await respond(route, { analysis_status: "completed", label: "phishing" }); });
  await select(page, "locked.eml"); await page.getByRole("button", { name: "Analyze", exact: true }).dblclick({ force: true });
  await expect(page.getByRole("button", { name: "Change file" })).toBeDisabled(); await expect(page.getByRole("button", { name: "Remove file" })).toBeDisabled();
  await drop(page, ["replacement.eml"]); await expect(page.getByText("locked.eml", { exact: true })).toBeVisible();
  await expect(page.getByText("Analyzing...", { exact: true }).last()).toBeVisible();
  await page.waitForTimeout(policy.polling.intervalMs + 300); expect(requests).toBe(1);
  await expect(page.getByLabel("Analysis status").getByRole("alert")).toHaveCount(0); release(); await expect(page.getByText("Result: Phishing")).toBeVisible(); await expect(page.locator(".status-result-area .filename")).toHaveText("locked.eml");
});
test("malformed success becomes a safe error; retry cooldown and two retries apply to every submission control", async ({ page }) => {
  await page.clock.install(); let requests = 0;
  await page.route("**/api/analyze", route => { requests++; return respond(route, { analysis_status: "completed", label: "safe" }); });
  await select(page); await page.getByRole("button", { name: "Analyze", exact: true }).click();
  const retry = page.getByRole("button", { name: "Retry", exact: true }); await expect(retry).toBeDisabled(); await expect(page.getByLabel("Analysis status").getByRole("alert")).toContainText("unavailable");
  for (let attempt = 0; attempt < policy.retry.maxRetries; attempt++) {
    await page.clock.fastForward(5000); await expect(retry).toBeEnabled(); await expect(page.getByRole("button", { name: "Analyze", exact: true })).toBeDisabled(); await retry.click(); await expect.poll(() => requests).toBe(attempt + 2); await expect(page.getByLabel("Analysis status").getByRole("alert")).toBeVisible();
  }
  await page.clock.fastForward(5000); await expect(retry).toBeDisabled(); await expect(page.getByText("Retry limit reached for this file. Choose another file.")).toBeVisible(); expect(requests).toBe(3);
  await expect(page.locator(".result-label")).toHaveCount(0);
});
test("browser timeout suppresses obsolete reply after a newer file attempt", async ({ page }) => {
  await page.clock.install(); let firstRoute: Route | undefined; let requests = 0;
  await page.route("**/api/analyze", async route => { requests++; if (requests === 1) firstRoute = route; else await respond(route, { analysis_status: "completed", label: "phishing" }); });
  await select(page, "old.eml"); await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await expect.poll(() => requests).toBe(1); await page.clock.fastForward(policy.deadlines.browserMs);
  await expect(page.getByLabel("Analysis status").getByRole("alert")).toContainText("timed out"); await select(page, "new.eml"); await page.getByRole("button", { name: "Analyze", exact: true }).click(); await expect(page.getByText("Result: Phishing")).toBeVisible();
  if (firstRoute) await respond(firstRoute, { analysis_status: "completed", label: "legit" }).catch(() => {});
  await expect(page.locator(".status-result-area .filename")).toHaveText("new.eml"); await expect(page.getByText("Result: Legit")).toHaveCount(0);
});
test("keyboard, phone, long filename and reduced-motion layout remain operable", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 700 }); await page.emulateMedia({ reducedMotion: "reduce" });
  await page.keyboard.press("Tab"); await expect(page.getByRole("button", { name: "Choose file", exact: true })).toBeFocused();
  const chooser = page.waitForEvent("filechooser"); await page.keyboard.press("Enter"); await (await chooser).setFiles(fixture("a".repeat(180) + ".eml"));
  await page.route("**/api/analyze", route => respond(route, { analysis_status: "completed", label: "legit" }));
  await page.getByRole("button", { name: "Analyze", exact: true }).focus(); await page.keyboard.press("Enter"); await expect(page.getByText("Result: Legit")).toBeVisible();
  await expect(page.getByLabel("Analysis status")).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.locator(".button").first().evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  await page.screenshot({ path: testInfo.outputPath("phone-result.png"), fullPage: true });
});
test("real local proxy with no configured service returns MODEL_UNAVAILABLE and no classification", async ({ page }) => {
  await select(page); await page.getByRole("button", { name: "Analyze", exact: true }).click(); await expect(page.getByLabel("Analysis status").getByRole("alert")).toContainText("Analysis is unavailable."); await expect(page.locator(".result-label")).toHaveCount(0);
});
test("keyboard Remove returns focus to described Choose file control", async ({ page }) => {
  await select(page);
  await expect(page.getByRole("button", { name: "Change file" })).toHaveAttribute("aria-describedby", "file-help");
  await page.getByRole("button", { name: "Remove file" }).focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Choose file", exact: true })).toBeFocused();
  await expect(page.getByRole("button", { name: "Choose file", exact: true })).toHaveAttribute("aria-describedby", "file-help");
  await drop(page, ["invalid.txt"]);
  await expect(page.getByRole("button", { name: "Choose another file" })).toHaveAttribute("aria-describedby", "file-help");
});
test("cooldown timers stop at expiry and are absent after retry exhaustion", async ({ page }) => {
  await page.clock.install();
  await page.evaluate(() => {
    const intervals = new Set<number>();
    const start = window.setInterval.bind(window); const stop = window.clearInterval.bind(window);
    window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => { const id = start(handler, timeout, ...args); if (timeout === 250) intervals.add(id); return id; }) as typeof window.setInterval;
    window.clearInterval = id => { if (typeof id === "number") intervals.delete(id); stop(id); };
    Object.defineProperty(window, "activeCooldownTimers", { get: () => intervals.size });
  });
  const timers = () => page.evaluate(() => (window as typeof window & { activeCooldownTimers: number }).activeCooldownTimers);
  let requests = 0;
  await page.route("**/api/analyze", route => { requests++; return respond(route, { error: { code: "SERVICE_BUSY", message: "Sample service busy" }, request_id: route.request().headers()["x-request-id"] }, 429); });
  await select(page); await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await expect.poll(timers).toBe(1);
  for (let attempt = 0; attempt < policy.retry.maxRetries; attempt++) {
    await page.clock.fastForward(5000); await expect.poll(timers).toBe(0);
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect.poll(() => requests).toBe(attempt + 2);
    await expect(page.getByLabel("Analysis status").getByRole("alert")).toBeVisible();
    await expect.poll(timers).toBe(attempt === policy.retry.maxRetries - 1 ? 0 : 1);
  }
  await page.clock.fastForward(30000); await expect.poll(timers).toBe(0);
});

test("a correlated observed processing phase is shown without widening the terminal result", async ({ page }) => {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/analyze", async route => {
    await pending;
    await respond(route, { analysis_status: "completed", label: "legit" });
  });
  await page.route("**/api/analysis-status?*", route => {
    const id = new URL(route.request().url()).searchParams.get("request_id")!;
    return route.fulfill({ status: 200, contentType: "application/json", headers: { "X-Request-ID": id }, body: JSON.stringify({ request_id: id, phase: "processing" }) });
  });
  await select(page, "observed.eml");
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await expect(page.getByText("Analyzing email...", { exact: true })).toBeVisible();
  await expect(page.locator(".result-label")).toHaveCount(0);
  release();
  await expect(page.getByText("Result: Legit", { exact: true })).toBeVisible();
  await expect(page.locator(".status-result-area .filename")).toHaveText("observed.eml");
});
