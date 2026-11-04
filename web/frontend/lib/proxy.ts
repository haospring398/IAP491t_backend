import { randomUUID } from "node:crypto";
import { errorEnvelope, isError, isJsonMediaType, isRequestId, isStatus, isSuccess, policy, type ErrorCode } from "./contracts";

export type ProxyConfig = { url: string; token: string } | null;
type Fetcher = typeof fetch;
class ProxyFailure extends Error {
  constructor(readonly code: ErrorCode) { super(code); }
}
function fail(code: ErrorCode, id: string) {
  const p = policy.errors[code];
  return Response.json(errorEnvelope(code, id), {
    status: p.http,
    headers: { "X-Request-ID": id, "Cache-Control": "no-store", ...(p.retryAfterSeconds ? { "Retry-After": String(p.retryAfterSeconds) } : {}) },
  });
}
function ok(body: unknown, id: string) {
  return Response.json(body, { headers: { "X-Request-ID": id, "Cache-Control": "no-store" } });
}

// Consume a bounded stream before invoking the multipart parser, even if length is absent or false.
export async function boundedBytes(stream: ReadableStream<Uint8Array> | null, limit: number, signal: AbortSignal) {
  if (!stream) return new Uint8Array();
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  const abort = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) abort();
  try {
    while (true) {
      if (signal.aborted) throw new ProxyFailure("ANALYSIS_TIMEOUT");
      const next = await reader.read();
      if (signal.aborted) throw new ProxyFailure("ANALYSIS_TIMEOUT");
      if (next.done) break;
      size += next.value.byteLength;
      if (size > limit) {
        void reader.cancel().catch(() => {});
        throw new ProxyFailure("EMAIL_TOO_LARGE");
      }
      chunks.push(next.value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return bytes;
  } finally { signal.removeEventListener("abort", abort); reader.releaseLock(); }
}

function endpoint(config: NonNullable<ProxyConfig>, path: string) {
  return new URL(path, config.url.endsWith("/") ? config.url : config.url + "/");
}
async function readWire(response: Response, signal: AbortSignal): Promise<unknown> {
  if (!isJsonMediaType(response.headers.get("Content-Type"))) {
    discardBody(response);
    throw new ProxyFailure("UPSTREAM_INVALID_RESPONSE");
  }
  try {
    const bytes = await boundedBytes(response.body, policy.limits.multipartBytes, signal);
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch (error) {
    if (signal.aborted) throw new ProxyFailure("ANALYSIS_TIMEOUT");
    if (error instanceof ProxyFailure && error.code === "ANALYSIS_TIMEOUT") throw error;
    throw new ProxyFailure("UPSTREAM_INVALID_RESPONSE");
  }
}
async function normalize(response: Response, id: string, signal: AbortSignal, statusChannel = false) {
  if (signal.aborted) { discardBody(response); throw new ProxyFailure("ANALYSIS_TIMEOUT"); }
  const correlated = response.headers.get("X-Request-ID") === id;
  if (!correlated) {
    discardBody(response);
    if (response.status === 503) throw new ProxyFailure("UPSTREAM_UNAVAILABLE");
    throw new ProxyFailure("UPSTREAM_INVALID_RESPONSE");
  }
  let data: unknown;
  try { data = await readWire(response, signal); }
  catch (error) {
    if (response.status === 503 && !signal.aborted) throw new ProxyFailure("UPSTREAM_UNAVAILABLE");
    throw error;
  }
  if (response.status === 200 && (statusChannel ? isStatus(data) && data.request_id === id : isSuccess(data))) return ok(data, id);
  if (isError(data) && data.request_id === id && response.status === policy.errors[data.error.code].http) {
    // Codes pass through; messages come from the shared safe copy, never exception/provider details.
    return fail(data.error.code, id);
  }
  throw new ProxyFailure("UPSTREAM_INVALID_RESPONSE");
}

function discardBody(response: Response) { void response.body?.cancel().catch(() => {}); }
function linkAbort(incoming: AbortSignal, controller: AbortController) {
  const abort = () => controller.abort();
  incoming.addEventListener("abort", abort, { once: true });
  if (incoming.aborted) abort();
  return () => incoming.removeEventListener("abort", abort);
}

export async function analyzeProxy(request: Request, config: ProxyConfig, fetcher: Fetcher = fetch): Promise<Response> {
  const entered = Date.now();
  const incomingId = request.headers.get("X-Request-ID");
  const id = isRequestId(incomingId) ? incomingId : randomUUID();
  if (!isRequestId(incomingId)) return fail("INVALID_REQUEST", id);
  const controller = new AbortController();
  const unlinkAbort = linkAbort(request.signal, controller);
  const timer = setTimeout(() => controller.abort(), policy.deadlines.proxyMs);
  const deadline = entered + policy.deadlines.proxyMs;
  try {
    if (controller.signal.aborted) throw new ProxyFailure("ANALYSIS_TIMEOUT");
    const contentType = request.headers.get("Content-Type") || "";
    if (!/^multipart\/form-data\s*;/i.test(contentType)) throw new ProxyFailure("INVALID_REQUEST");
    const declared = request.headers.get("Content-Length");
    if (declared && /^\d+$/.test(declared) && Number(declared) > policy.limits.multipartBytes) throw new ProxyFailure("EMAIL_TOO_LARGE");
    const bytes = await boundedBytes(request.body, policy.limits.multipartBytes, controller.signal);
    let form: FormData;
    try { form = await new Response(bytes, { headers: { "Content-Type": contentType } }).formData(); }
    catch { throw new ProxyFailure("INVALID_REQUEST"); }
    if (controller.signal.aborted || Date.now() >= deadline) throw new ProxyFailure("ANALYSIS_TIMEOUT");
    const entries = [...form.entries()];
    if (entries.length !== 1 || entries[0][0] !== "file" || typeof entries[0][1] === "string") throw new ProxyFailure("INVALID_REQUEST");
    const file = entries[0][1];
    if (!/\.eml$/i.test(file.name)) throw new ProxyFailure("INVALID_REQUEST");
    if (file.size === 0) throw new ProxyFailure("EMPTY_EMAIL");
    if (file.size > policy.limits.fileBytes) throw new ProxyFailure("EMAIL_TOO_LARGE");
    if (!config) throw new ProxyFailure("MODEL_UNAVAILABLE");
    const forwarded = new FormData();
    forwarded.append("file", file, "message.eml");
    let upstream: Response;
    try {
      upstream = await fetcher(endpoint(config, "v1/analyze"), {
        method: "POST", body: forwarded, signal: controller.signal, redirect: "error", cache: "no-store",
        headers: { Authorization: `Bearer ${config.token}`, "X-Request-ID": id, "X-Analysis-Deadline": String(deadline) },
      });
    } catch {
      throw new ProxyFailure(controller.signal.aborted ? "ANALYSIS_TIMEOUT" : "UPSTREAM_UNAVAILABLE");
    }
    return await normalize(upstream, id, controller.signal);
  } catch (error) { return fail(error instanceof ProxyFailure ? error.code : "INTERNAL_ERROR", id); }
  finally { clearTimeout(timer); unlinkAbort(); }
}

export async function statusProxy(request: Request, config: ProxyConfig, fetcher: Fetcher = fetch) {
  const params = new URL(request.url).searchParams;
  const incomingId = params.get("request_id");
  const id = isRequestId(incomingId) ? incomingId : randomUUID();
  if (!isRequestId(incomingId) || [...params].length !== 1) return fail("INVALID_REQUEST", id);
  if (!config) return fail("MODEL_UNAVAILABLE", id);
  const controller = new AbortController();
  const unlinkAbort = linkAbort(request.signal, controller);
  const timer = setTimeout(() => controller.abort(), policy.polling.timeoutMs);
  try {
    if (controller.signal.aborted) throw new ProxyFailure("ANALYSIS_TIMEOUT");
    const url = endpoint(config, "v1/analysis-status");
    url.searchParams.set("request_id", id);
    let upstream: Response;
    try {
      upstream = await fetcher(url, { signal: controller.signal, redirect: "error", cache: "no-store", headers: { Authorization: `Bearer ${config.token}` } });
    } catch { throw new ProxyFailure(controller.signal.aborted ? "ANALYSIS_TIMEOUT" : "UPSTREAM_UNAVAILABLE"); }
    return await normalize(upstream, id, controller.signal, true);
  } catch (error) { return fail(error instanceof ProxyFailure ? error.code : "INTERNAL_ERROR", id); }
  finally { clearTimeout(timer); unlinkAbort(); }
}
