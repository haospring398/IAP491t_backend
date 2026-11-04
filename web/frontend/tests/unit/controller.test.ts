import { test } from "node:test";
import assert from "node:assert/strict";
import { AnalysisController, selectionError } from "../../lib/analysis-controller";
import { AnalysisFailure, createBrowserTransport, pollStatus, type AnalyzeTransport } from "../../lib/client";
import { policy, type AnalysisSuccess } from "../../lib/contracts";
const id = "672f0ea9-e237-45cd-8c08-8710f89b8258";
const file = new File(["Subject: fixture\r\n\r\nFixture body"], "fixture.eml");
const settle = () => new Promise<void>(resolve => setImmediate(resolve));
function deferred() { let resolve!: (data: AnalysisSuccess) => void; const promise = new Promise<AnalysisSuccess>(r => { resolve = r; }); return { promise, resolve }; }
test("selection rejects multiples/empty/size/extension without reading MIME; cancellation preserves state", async () => {
  assert.equal(selectionError([file, file]), "INVALID_REQUEST");
  assert.equal(selectionError([new File([], "empty.eml")]), "EMPTY_EMAIL");
  assert.equal(selectionError([new File(["x"], "wrong.txt")]), "INVALID_REQUEST");
  assert.equal(selectionError([new File([new Uint8Array(policy.limits.fileBytes + 1)], "big.eml")]), "EMAIL_TOO_LARGE");
  const controller = new AnalysisController(async () => ({ analysis_status: "completed", label: "legit" }));
  controller.select([file]); const selected = controller.getSnapshot(); controller.select([]); assert.equal(controller.getSnapshot(), selected);
  controller.start(); await settle(); const success = controller.getSnapshot(); controller.select([]); assert.equal(controller.getSnapshot(), success);
  controller.select([new File(["x"], "bad.txt")]); assert.equal(controller.getSnapshot().state, "error"); assert(!("label" in controller.getSnapshot()));
});
test("attempt lock is synchronous, preserves captured filename, and locks drops/removal", async () => {
  const reply = deferred(); let requests = 0;
  const transport: AnalyzeTransport = (_file, _id, _signal, phase) => { requests++; phase("processing"); return reply.promise; };
  const controller = new AnalysisController(transport);
  controller.select([file]); assert(controller.start()); assert(!controller.start());
  controller.select([new File(["different"], "different.eml")]); controller.remove();
  assert.equal(controller.getSnapshot().file, file); assert.equal(requests, 1);
  reply.resolve({ analysis_status: "completed", label: "phishing" }); await settle();
  const state = controller.getSnapshot(); assert.equal(state.state, "success"); if (state.state === "success") { assert.equal(state.filename, file.name); assert.equal(state.label, "phishing"); }
  controller.remove(); assert.equal(controller.getSnapshot().state, "no-file");
});
test("success carries the explanation and replacement, removal or failure clears it", async () => {
  const explanation = { factors: [{ factor: "num_attachments", direction: "positive", strength: 1 }] } as AnalysisSuccess["explanation"];
  let fail = false;
  const controller = new AnalysisController(async () => { if (fail) throw new AnalysisFailure("SERVICE_BUSY"); return { analysis_status: "completed", label: "phishing", explanation }; });
  controller.select([file]); controller.start(); await settle();
  const state = controller.getSnapshot(); assert.equal(state.state, "success"); if (state.state === "success") assert.deepEqual(state.explanation, explanation);
  controller.select([file]); assert(!("explanation" in controller.getSnapshot()));
  controller.start(); await settle(); controller.remove(); assert.equal(controller.getSnapshot().state, "no-file"); assert(!("explanation" in controller.getSnapshot()));
  controller.select([file]); controller.start(); await settle(); fail = true; controller.select([file]); controller.start(); await settle();
  assert.equal(controller.getSnapshot().state, "error"); assert(!("explanation" in controller.getSnapshot()));
  const plain = new AnalysisController(async () => ({ analysis_status: "completed", label: "legit" }));
  plain.select([file]); plain.start(); await settle(); assert(!("explanation" in plain.getSnapshot()));
});
test("all start actions share cooldown and exactly two retries; replacement resets and input errors discard", async () => {
  let now = 1000; let requests = 0;
  const controller = new AnalysisController(async () => { requests++; throw new AnalysisFailure("SERVICE_BUSY"); }, () => now);
  controller.select([file]); controller.start(); await settle(); assert(!controller.start());
  now += 4999; assert(!controller.start()); now++; assert(controller.start()); await settle();
  now += 5000; assert(controller.start()); await settle(); now += 5000; assert(!controller.start()); assert.equal(requests, 3);
  controller.select([file]); assert(controller.start()); await settle(); assert.equal(requests, 4);
  const invalid = new AnalysisController(async () => { throw new AnalysisFailure("INVALID_EMAIL"); }); invalid.select([file]); invalid.start(); await settle(); assert.equal(invalid.getSnapshot().file, null); assert(!invalid.start());
});
test("timeout invalidates identity and suppresses late reply; unmount disposes active attempt", async t => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const reply = deferred(); const controller = new AnalysisController(() => reply.promise);
  controller.select([file]); controller.start(); t.mock.timers.tick(policy.deadlines.browserMs);
  assert.equal(controller.getSnapshot().state, "error"); reply.resolve({ analysis_status: "completed", label: "legit" }); await settle(); assert.equal(controller.getSnapshot().state, "error");
  const late = deferred(); const disposed = new AnalysisController(() => late.promise); disposed.select([file]); disposed.start(); disposed.dispose(); late.resolve({ analysis_status: "completed", label: "phishing" }); await settle(); assert.equal(disposed.getSnapshot().state, "analyzing");
});
test("browser rejects stale IDs, aliases and unexpected status; polls cannot commit/fail the terminal POST", async () => {
  const signal = new AbortController().signal;
  for (const [body, header, status] of [[{ analysis_status: "completed", label: "safe" }, id, 200], [{ analysis_status: "completed", label: "legit" }, "stale", 200], [{ analysis_status: "completed", label: "legit" }, id, 201]] as const) {
    const transport = createBrowserTransport(async () => Response.json(body, { status, headers: { "X-Request-ID": header } }));
    await assert.rejects(transport(file, id, signal, () => {}), /unavailable/);
  }
  const transport = createBrowserTransport(async () => Response.json({ analysis_status: "completed", label: "phishing" }, { headers: { "X-Request-ID": id } }));
  assert.equal((await transport(file, id, signal, () => {})).label, "phishing");
});
test("status polls do not overlap and abort stops late progress", async t => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  let requests = 0; let reply!: (r: Response) => void; let phases = 0;
  const fetcher: typeof fetch = async () => { requests++; return new Promise<Response>(r => { reply = r; }); };
  const abort = new AbortController(); const stop = pollStatus(id, abort.signal, () => { phases++; }, fetcher);
  t.mock.timers.tick(policy.polling.intervalMs); assert.equal(requests, 1);
  t.mock.timers.tick(8000); assert.equal(requests, 1); abort.abort();
  reply(Response.json({ request_id: id, phase: "processing" }, { headers: { "X-Request-ID": id } })); await settle(); t.mock.timers.tick(5000); assert.equal(requests, 1); assert.equal(phases, 0); stop();
});
test("status JSON served as text/plain cannot announce a phase", async t => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const phases: string[] = [];
  const abort = new AbortController();
  const stop = pollStatus(id, abort.signal, phase => phases.push(phase), async () => new Response(JSON.stringify({ request_id: id, phase: "processing" }), { headers: { "X-Request-ID": id, "Content-Type": "text/plain" } }));
  t.mock.timers.tick(policy.polling.intervalMs); await settle();
  assert.deepEqual(phases, ["unknown"]); stop();
});
