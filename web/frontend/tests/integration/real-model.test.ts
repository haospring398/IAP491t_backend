import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { existsSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { randomUUID } from "node:crypto";
import { chromium } from "@playwright/test";
import { factorCatalogue } from "../../lib/contracts";

// Backend chạy độc lập từ web/ (python -m backend), không cần thư mục gốc của project.
const webRoot = fileURLToPath(new URL("../../../", import.meta.url));
// Python cho backend: IAP_WEB_PYTHON, rồi web/.venv, rồi .venv ở thư mục gốc repository.
function backendPython() {
  if (process.env.IAP_WEB_PYTHON) return process.env.IAP_WEB_PYTHON;
  const relative = process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python";
  const found = [webRoot, path.join(webRoot, "..")].map(folder => path.join(folder, relative)).find(existsSync);
  if (!found) assert.fail("No Python for the backend: set IAP_WEB_PYTHON or create web/.venv from backend/requirements.txt");
  return found;
}
async function freePort() {
  const server = createServer(); server.listen(0, "127.0.0.1"); await once(server, "listening");
  const port = (server.address() as { port: number }).port;
  await new Promise<void>(resolve => server.close(() => resolve())); return port;
}
async function stop(child: ChildProcess) {
  if (child.exitCode !== null) return;
  const exited = once(child, "exit");
  if (process.platform === "win32") {
    const cleanup = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
    await once(cleanup, "exit");
  } else child.kill();
  await exited;
}
async function waitFor(url: string, child: ChildProcess, limit: number) {
  const deadline = Date.now() + limit;
  while (Date.now() < deadline) {
    assert.equal(child.exitCode, null, "Local service exited during startup");
    try { if ((await fetch(url, { signal: AbortSignal.timeout(3000) })).status === 200) return; } catch {}
    await delay(100);
  }
  throw new Error("Local service readiness timeout");
}

test("actual pinned model: five MIME cases through Python, Next proxy and browser; unavailable clears result", { timeout: 180000 }, async t => {
  const token = randomUUID();
  const backendPort = await freePort(), frontendPort = await freePort();
  const api = `http://127.0.0.1:${backendPort}`, web = `http://127.0.0.1:${frontendPort}`;
  const python = backendPython();
  const backend = spawn(python, ["-m", "backend", "--port", String(backendPort)], {
    // IAP_WEB_MODEL rỗng: kiểm đúng model pin trong policy.py, không lấy giá trị từ shell.
    cwd: webRoot, windowsHide: true, stdio: "ignore", env: { ...process.env, ML_API_TOKEN: token, IAP_WEB_MODEL: "" },
  });
  t.after(() => stop(backend));
  await waitFor(`${api}/health/ready`, backend, 120000);
  const next = spawn(process.execPath, ["node_modules/next/dist/bin/next", process.env.FRONTEND_TEST_DEV === "1" ? "dev" : "start", "--hostname", "127.0.0.1", "--port", String(frontendPort)], {
    cwd: process.cwd(), windowsHide: true, stdio: "ignore",
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1", ML_API_URL: api, ML_API_TOKEN: token },
  });
  t.after(() => stop(next));
  await waitFor(web, next, 60000);
  const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL });
  t.after(() => browser.close());
  const page = await browser.newPage(); await page.goto(web);
  assert.match(await page.getByRole("note").innerText(), /phishing detection accuracy has not been independently established/);
  const labelText: Record<string, string> = { legit: "Legit", phishing: "Phishing", spam_or_phishing: "Spam / phishing" };
  const samples = new URL("../../../backend/samples/", import.meta.url);
  const names = (await readdir(samples)).filter(name => name.endsWith(".eml")).sort();
  assert.equal(names.length, 5);
  for (const name of names) {
    const bytes = await readFile(new URL(name, samples));
    const form = new FormData(); form.append("file", new File([bytes], "message.eml"));
    const direct = await fetch(`${api}/v1/analyze`, { method: "POST", body: form,
      headers: { Authorization: `Bearer ${token}`, "X-Request-ID": randomUUID(), "X-Analysis-Deadline": String(Date.now() + 150000) } });
    assert.equal(direct.status, 200);
    const expected = await direct.json() as { analysis_status: string; label: string; explanation?: { factors: { factor: string }[] } };
    // Web phục vụ XGBoost được pin của run baseline_v6 với target phishing nên phải có explanation (AD-14).
    assert.deepEqual(Object.keys(expected).sort(), ["analysis_status", "explanation", "label"]);
    assert(expected.label in labelText);
    const filename = `browser-${name}`;
    await page.locator("#email-file").setInputFiles({ name: filename, mimeType: "message/rfc822", buffer: bytes });
    const response = page.waitForResponse(r => r.url() === `${web}/api/analyze` && r.request().method() === "POST");
    await page.getByRole("button", { name: "Analyze", exact: true }).click();
    assert.deepEqual(await (await response).json(), expected);
    await page.locator(".result-label").waitFor();
    assert.equal(await page.locator(".result-label").innerText(), `Result: ${labelText[expected.label]}`);
    assert.equal(await page.locator(".status-result-area .filename").innerText(), filename);
    const shown = page.locator(".explanation-list li .factor-name");
    assert.deepEqual(await shown.allInnerTexts(), expected.explanation!.factors.map(item => factorCatalogue[item.factor].label));
  }
  await stop(backend);
  await page.locator("#email-file").setInputFiles({ name: "unavailable.eml", mimeType: "message/rfc822", buffer: await readFile(new URL("plain.eml", samples)) });
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await page.getByLabel("Analysis status").getByRole("alert").waitFor();
  assert.equal(await page.locator(".result-label").count(), 0);
  assert.equal(await page.locator(".explanation-list").count(), 0);
  assert.match(await page.getByLabel("Analysis status").getByRole("alert").innerText(), /could not be reached/);
});
