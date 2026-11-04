import { test } from "node:test";
import assert from "node:assert/strict";
import { analyzeProxy, boundedBytes, statusProxy } from "../../lib/proxy";
import { isRequestId, policy } from "../../lib/contracts";
const id = "672f0ea9-e237-45cd-8c08-8710f89b8258";
const config = { url: "https://ml.example.test", token: "server-token-fixture" };
function upload(name = "private.EML", size = 32, extra?: (form: FormData) => void) {
  const body = new FormData(); body.append("file", new File([new Uint8Array(size)], name)); extra?.(body);
  return new Request("http://127.0.0.1/api/analyze", { method: "POST", body, headers: { "X-Request-ID": id, "X-Analysis-Deadline": "1" } });
}
function wire(body: unknown, status = 200, requestId = id) { return Response.json(body, { status, headers: { "X-Request-ID": requestId } }); }
function stub(response: Response): typeof fetch { return async () => response; }
async function code(response: Response) { return (await response.json()).error.code; }
test("forward canonical filename, sole part, server token and newly trusted deadline; correlate both labels", async () => {
  for (const label of ["legit", "spam_or_phishing", "phishing"]) {
    const before = Date.now();
    const response = await analyzeProxy(upload(), config, async (url, init) => {
      assert.equal(String(url), "https://ml.example.test/v1/analyze");
      const headers = new Headers(init?.headers);
      assert.equal(headers.get("Authorization"), `Bearer ${config.token}`);
      assert.equal(headers.get("X-Request-ID"), id);
      assert(Number(headers.get("X-Analysis-Deadline")) >= before + policy.deadlines.proxyMs);
      assert.equal(init?.redirect, "error");
      const form = init?.body as FormData;
      assert.deepEqual([...form.keys()], ["file"]);
      assert.equal((form.get("file") as File).name, "message.eml");
      return wire({ analysis_status: "completed", label });
    });
    assert.equal(response.status, 200); assert.equal(response.headers.get("X-Request-ID"), id);
    assert.deepEqual(await response.json(), { analysis_status: "completed", label });
  }
  const explained = { analysis_status: "completed", label: "phishing", explanation: { factors: [{ factor: "num_attachments", direction: "positive", strength: 1 }] } };
  const response = await analyzeProxy(upload(), config, stub(wire(explained)));
  assert.equal(response.status, 200); assert.deepEqual(await response.json(), explained);
});
test("invalid multipart/input never forwards and missing identity gets a fresh correlated error", async () => {
  let requests = 0; const fetcher: typeof fetch = async () => { requests++; throw Error("should not forward"); };
  for (const [request, expected] of [
    [upload("bad.txt"), "INVALID_REQUEST"], [upload("empty.eml", 0), "EMPTY_EMAIL"],
    [upload("big.eml", policy.limits.fileBytes + 1), "EMAIL_TOO_LARGE"],
    [upload("a.eml", 32, form => form.append("file", new File(["b"], "b.eml"))), "INVALID_REQUEST"],
    [upload("a.eml", 32, form => form.append("metadata", "x")), "INVALID_REQUEST"],
    [new Request("http://localhost/api/analyze", { method: "POST", body: "invalid", headers: { "X-Request-ID": id, "Content-Type": "multipart/form-data; boundary=nope" } }), "INVALID_REQUEST"],
  ] as const) assert.equal(await code(await analyzeProxy(request, config, fetcher)), expected);
  const missing = await analyzeProxy(new Request("http://localhost/api/analyze", { method: "POST" }), config, fetcher);
  assert(isRequestId(missing.headers.get("X-Request-ID")));
  const data = await missing.json(); assert.equal(data.request_id, missing.headers.get("X-Request-ID")); assert.equal(data.error.code, "INVALID_REQUEST");
  assert.equal(requests, 0);
});
test("exact file limit succeeds; actual body overrun rejects regardless of declared length", async () => {
  assert.equal((await analyzeProxy(upload("edge.eml", policy.limits.fileBytes), config, stub(wire({ analysis_status: "completed", label: "legit" })))).status, 200);
  for (const declared of [undefined, "1"]) {
    const headers: Record<string, string> = { "X-Request-ID": id, "Content-Type": "multipart/form-data; boundary=test" };
    if (declared) headers["Content-Length"] = declared;
    const request = new Request("http://localhost/api/analyze", { method: "POST", headers, body: new Uint8Array(policy.limits.multipartBytes + 1) });
    assert.equal(await code(await analyzeProxy(request, config)), "EMAIL_TOO_LARGE");
  }
});
test("unconfigured backend returns MODEL_UNAVAILABLE; errors contain safe copy and shared cooldown", async () => {
  assert.equal(await code(await analyzeProxy(upload(), null)), "MODEL_UNAVAILABLE");
  for (const [errorCode, value] of Object.entries(policy.errors)) {
    const upstream = wire({ error: { code: errorCode, message: "private-provider-detail" }, request_id: id }, value.http);
    const response = await analyzeProxy(upload(), config, stub(upstream));
    assert.equal(response.status, value.http); assert.equal(response.headers.get("Retry-After"), value.retryAfterSeconds ? String(value.retryAfterSeconds) : null);
    const body = await response.json(); assert.equal(body.error.code, errorCode); assert.equal(body.error.message, value.message); assert(!("label" in body));
  }
});
test("provider/auth/malformed/extraneous/stale replies and transport failures normalize without leaking", async () => {
  for (const [response, expected] of [
    [new Response("<html>provider-secret</html>", { status: 503 }), "UPSTREAM_UNAVAILABLE"],
    [new Response("auth-secret", { status: 401 }), "UPSTREAM_INVALID_RESPONSE"],
    [wire({ analysis_status: "completed", label: "safe" }), "UPSTREAM_INVALID_RESPONSE"],
    [wire({ analysis_status: "completed", label: "phishing", indicators: [] }), "UPSTREAM_INVALID_RESPONSE"],
    [wire({ analysis_status: "completed", label: "phishing", explanation: { factors: [{ factor: "unknown_feature", direction: "positive", strength: 1 }] } }), "UPSTREAM_INVALID_RESPONSE"],
    [wire({ analysis_status: "completed", label: "phishing", explanation: { factors: [{ factor: "num_attachments", direction: "positive", strength: 1 }, { factor: "num_attachments", direction: "negative", strength: 0.5 }] } }), "UPSTREAM_INVALID_RESPONSE"],
    [wire({ analysis_status: "completed", label: "phishing" }, 200, "stale-id"), "UPSTREAM_INVALID_RESPONSE"],
    [new Response("not-json", { headers: { "Content-Type": "application/json", "X-Request-ID": id } }), "UPSTREAM_INVALID_RESPONSE"],
    [wire({ analysis_status: "completed", label: "legit" }, 201), "UPSTREAM_INVALID_RESPONSE"],
  ] as const) assert.equal(await code(await analyzeProxy(upload(), config, stub(response))), expected);
  assert.equal(await code(await analyzeProxy(upload(), config, async () => { throw Error("provider-secret"); })), "UPSTREAM_UNAVAILABLE");
});
test("abort releases a stalled upload reader within the trusted budget", async () => {
  const abort = new AbortController();
  let cancelled = false;
  const pending = boundedBytes(new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } }), policy.limits.multipartBytes, abort.signal);
  abort.abort(); await assert.rejects(pending, /ANALYSIS_TIMEOUT/); assert(cancelled);
});
test("status query is sole v4 ID; strict correlated envelope only, no labels", async () => {
  const request = new Request(`http://localhost/api/analysis-status?request_id=${id}`);
  assert.equal((await statusProxy(request, config, stub(wire({ request_id: id, phase: "starting" })))).status, 200);
  assert.equal(await code(await statusProxy(request, config, stub(wire({ request_id: id, phase: "processing", label: "legit" })))), "UPSTREAM_INVALID_RESPONSE");
  assert.equal(await code(await statusProxy(new Request(`http://localhost/api/analysis-status?request_id=${id}&request_id=${id}`), config)), "INVALID_REQUEST");
  assert.equal(await code(await statusProxy(new Request("http://localhost/api/analysis-status?request_id=no"), config)), "INVALID_REQUEST");
});
const settle = () => new Promise<void>(resolve => setImmediate(resolve));
async function assertTimeout(response: Response) {
  assert.equal(response.status, 504); assert.equal(response.headers.get("X-Request-ID"), id);
  assert.deepEqual(await response.json(), { request_id: id, error: { code: "ANALYSIS_TIMEOUT", message: policy.errors.ANALYSIS_TIMEOUT.message } });
}
function stalledUpload(signal?: AbortSignal) {
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } });
  const request = new Request("http://localhost/api/analyze", { method: "POST", headers: { "X-Request-ID": id, "Content-Type": "multipart/form-data; boundary=fixture" }, body, signal, duplex: "half" } as RequestInit & { duplex: "half" });
  return { request, cancelled: () => cancelled };
}
test("early upstream correlation/media-type rejection cancels unread streaming bodies", async () => {
  for (const headers of [{ "X-Request-ID": "stale", "Content-Type": "application/json" }, { "X-Request-ID": id, "Content-Type": "text/html" }]) {
    let cancelled = false;
    const upstream = new Response(new ReadableStream({ cancel() { cancelled = true; } }), { headers });
    const response = await analyzeProxy(upload(), config, stub(upstream));
    assert.equal(await code(response), "UPSTREAM_INVALID_RESPONSE"); assert(cancelled);
  }
});
test("actual proxy timer cancels a stalled upload and returns correlated timeout", async t => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const incoming = stalledUpload(); const pending = analyzeProxy(incoming.request, config);
  t.mock.timers.tick(policy.deadlines.proxyMs); await assertTimeout(await pending); assert(incoming.cancelled());
});
test("actual proxy timer aborts upstream fetch; forwarded deadline remains independently trusted", async t => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 10000 });
  let cancelled = false; let deadline = "";
  let fetched!: () => void; const started = new Promise<void>(resolve => { fetched = resolve; });
  const pending = analyzeProxy(upload(), config, async (_url, init) => {
    deadline = new Headers(init?.headers).get("X-Analysis-Deadline")!;
    fetched();
    return new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener("abort", () => { cancelled = true; reject(new Error("private abort detail")); }, { once: true }));
  });
  await started; assert.equal(deadline, String(10000 + policy.deadlines.proxyMs));
  t.mock.timers.tick(policy.deadlines.proxyMs); await assertTimeout(await pending); assert(cancelled);
});
test("actual proxy timer cancels stalled upstream JSON consumption", async t => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  let cancelled = false;
  let fetched!: () => void; const started = new Promise<void>(resolve => { fetched = resolve; });
  const upstream = new Response(new ReadableStream({ cancel() { cancelled = true; } }), { headers: { "X-Request-ID": id, "Content-Type": "application/json" } });
  const pending = analyzeProxy(upload(), config, async () => { fetched(); return upstream; }); await started; await settle();
  t.mock.timers.tick(policy.deadlines.proxyMs); await assertTimeout(await pending); assert(cancelled);
});
test("status timer aborts fetch and cancels stalled response bodies", async t => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const request = () => new Request(`http://localhost/api/analysis-status?request_id=${id}`);
  let aborted = false;
  const pendingFetch = statusProxy(request(), config, async (_url, init) => new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener("abort", () => { aborted = true; reject(Error("fixture")); }, { once: true })));
  t.mock.timers.tick(policy.polling.timeoutMs); await assertTimeout(await pendingFetch); assert(aborted);
  let cancelled = false;
  const upstream = new Response(new ReadableStream({ cancel() { cancelled = true; } }), { headers: { "X-Request-ID": id, "Content-Type": "application/json" } });
  const pendingBody = statusProxy(request(), config, stub(upstream)); await settle();
  t.mock.timers.tick(policy.polling.timeoutMs); await assertTimeout(await pendingBody); assert(cancelled);
});
test("incoming abort cancels upload, analysis fetch and status fetch", async () => {
  const uploadAbort = new AbortController(); const incoming = stalledUpload(uploadAbort.signal);
  const pendingUpload = analyzeProxy(incoming.request, config); uploadAbort.abort(); await assertTimeout(await pendingUpload); assert(incoming.cancelled());
  for (const status of [false, true]) {
    const incomingAbort = new AbortController(); let cancelled = false;
    let fetched!: () => void; const started = new Promise<void>(resolve => { fetched = resolve; });
    const request = status ? new Request(`http://localhost/api/analysis-status?request_id=${id}`, { signal: incomingAbort.signal }) : new Request(upload(), { signal: incomingAbort.signal });
    const fetcher: typeof fetch = async (_url, init) => { fetched(); return new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener("abort", () => { cancelled = true; reject(Error("private abort detail")); }, { once: true })); };
    const pending = status ? statusProxy(request, config, fetcher) : analyzeProxy(request, config, fetcher);
    await started; incomingAbort.abort(); await assertTimeout(await pending); assert(cancelled);
  }
});
test("request abort listeners are removed after both terminal routes", async () => {
  for (const status of [false, true]) {
    const incoming = new AbortController(); let forwarded: AbortSignal | undefined;
    const request = status ? new Request(`http://localhost/api/analysis-status?request_id=${id}`, { signal: incoming.signal }) : new Request(upload(), { signal: incoming.signal });
    const fetcher: typeof fetch = async (_url, init) => { forwarded = init?.signal as AbortSignal; return wire(status ? { request_id: id, phase: "processing" } : { analysis_status: "completed", label: "legit" }); };
    const response = await (status ? statusProxy(request, config, fetcher) : analyzeProxy(request, config, fetcher));
    assert.equal(response.status, 200); incoming.abort(); assert.equal(forwarded?.aborted, false);
  }
});
