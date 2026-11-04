import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { setTimeout as delay } from "node:timers/promises";
import { policy } from "../../lib/contracts";
const id = "672f0ea9-e237-45cd-8c08-8710f89b8258";
const token = "sample-configured-route-token";
async function listen(server: Server) { server.listen(0, "127.0.0.1"); await once(server, "listening"); return (server.address() as { port: number }).port; }
async function close(server: Server) { server.closeAllConnections(); await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }

test("Sample result — not a real analysis: configured Next routes serialize and authenticate the separate HTTP service", { timeout: 60000 }, async t => {
  const observed: { path: string; bearer: string | undefined; id?: string; deadline?: string; bytes?: Buffer; type?: string }[] = [];
  const fixture = createServer(async (request, response) => {
    const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
    const url = new URL(request.url!, "http://fixture.test");
    const requestId = request.headers["x-request-id"] as string | undefined;
    observed.push({ path: url.pathname, bearer: request.headers.authorization, id: requestId, deadline: request.headers["x-analysis-deadline"] as string | undefined, bytes: Buffer.concat(chunks), type: request.headers["content-type"] });
    const correlation = url.pathname.endsWith("analysis-status") ? url.searchParams.get("request_id")! : requestId!;
    response.writeHead(200, { "Content-Type": "application/json", "X-Request-ID": correlation });
    response.end(JSON.stringify(url.pathname.endsWith("analysis-status") ? { request_id: correlation, phase: "processing" } : { analysis_status: "completed", label: "legit" }));
  });
  const backendPort = await listen(fixture); t.after(() => close(fixture));
  const portProbe = createServer(); const frontendPort = await listen(portProbe); await close(portProbe);
  const mode = process.env.FRONTEND_TEST_DEV === "1" ? "dev" : "start";
  const next = spawn(process.execPath, ["node_modules/next/dist/bin/next", mode, "--hostname", "127.0.0.1", "--port", String(frontendPort)], {
    cwd: process.cwd(), windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1", ML_API_URL: `http://127.0.0.1:${backendPort}`, ML_API_TOKEN: token },
  });
  let output = ""; next.stdout.on("data", chunk => { output += chunk; }); next.stderr.on("data", chunk => { output += chunk; });
  t.after(async () => {
    if (next.exitCode === null) {
      const exited = once(next, "exit");
      if (process.platform === "win32") {
        const cleanup = spawn("taskkill", ["/PID", String(next.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
        await once(cleanup, "exit");
      } else next.kill();
      await exited;
    }
  });
  const root = `http://127.0.0.1:${frontendPort}`;
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (next.exitCode !== null) throw Error(`Next fixture server exited: ${output}`);
    try { const response = await fetch(`${root}/api/analysis-status?request_id=${id}`, { signal: AbortSignal.timeout(5000) }); if (response.status === 200) { ready = true; break; } } catch {}
    await delay(200);
  }
  assert(ready, `Next fixture server did not start: ${output}`); observed.length = 0;
  const email = "From: sample@example.test\r\nSubject: Sample result - not a real analysis\r\n\r\nTest-only fixture body.";
  const form = new FormData(); form.append("file", new File([email], "private-original.EML", { type: "message/rfc822" }));
  const started = Date.now();
  const response = await fetch(`${root}/api/analyze`, { method: "POST", body: form, headers: { "X-Request-ID": id, "X-Analysis-Deadline": "1" } });
  assert.equal(response.status, 200); assert.equal(response.headers.get("X-Request-ID"), id);
  assert.deepEqual(await response.json(), { analysis_status: "completed", label: "legit" });
  const analysis = observed.find(item => item.path === "/v1/analyze")!;
  assert(analysis); assert.equal(analysis.bearer, `Bearer ${token}`); assert.equal(analysis.id, id);
  assert(Number(analysis.deadline) >= started + policy.deadlines.proxyMs);
  assert(Number(analysis.deadline) <= Date.now() + policy.deadlines.proxyMs);
  assert.match(analysis.type!, /^multipart\/form-data; boundary=/);
  const forwarded = await new Response(new Uint8Array(analysis.bytes!), { headers: { "Content-Type": analysis.type! } }).formData();
  assert.deepEqual([...forwarded.keys()], ["file"]); const file = forwarded.get("file") as File;
  assert.equal(file.name, "message.eml"); assert.equal(await file.text(), email);
  assert(!analysis.bytes!.includes(Buffer.from("private-original.EML")));
  const status = await fetch(`${root}/api/analysis-status?request_id=${id}`);
  assert.equal(status.status, 200); assert.equal(status.headers.get("X-Request-ID"), id);
  assert.deepEqual(await status.json(), { request_id: id, phase: "processing" });
  assert.equal(observed.find(item => item.path === "/v1/analysis-status")?.bearer, `Bearer ${token}`);
});
