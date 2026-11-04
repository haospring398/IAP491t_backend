import { isError, isJsonMediaType, isStatus, isSuccess, policy, type AnalysisSuccess, type AnalysisStatus, type ErrorCode } from "./contracts";
export class AnalysisFailure extends Error {
  constructor(readonly code: ErrorCode) { super(policy.errors[code].message); }
}
export type Phase = AnalysisStatus["phase"];
export type AnalyzeTransport = (file: File, id: string, signal: AbortSignal, onPhase: (phase: Phase) => void) => Promise<AnalysisSuccess>;

export function pollStatus(id: string, signal: AbortSignal, onPhase: (phase: Phase) => void, fetcher: typeof fetch = fetch) {
  let active = true;
  let polls = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pending: AbortController | undefined;
  const expires = Date.now() + policy.deadlines.browserMs;
  const stop = () => { active = false; clearTimeout(timer); pending?.abort(); signal.removeEventListener("abort", stop); };
  const schedule = () => {
    if (active && !signal.aborted && polls < policy.polling.maxPolls && Date.now() < expires) timer = setTimeout(run, policy.polling.intervalMs);
  };
  async function run() {
    if (!active || signal.aborted) return;
    polls++;
    pending = new AbortController();
    const timeout = setTimeout(() => pending?.abort(), policy.polling.timeoutMs);
    try {
      const response = await fetcher(`/api/analysis-status?request_id=${encodeURIComponent(id)}`, { signal: pending.signal, cache: "no-store" });
      if (!isJsonMediaType(response.headers.get("Content-Type"))) {
        void response.body?.cancel().catch(() => {});
        if (active && !signal.aborted) onPhase("unknown");
        return;
      }
      const data: unknown = await response.json();
      if (active && !signal.aborted) {
        onPhase(response.status === 200 && response.headers.get("X-Request-ID") === id && isStatus(data) && data.request_id === id ? data.phase : "unknown");
      }
    } catch { if (active && !signal.aborted) onPhase("unknown"); }
    finally { clearTimeout(timeout); pending = undefined; schedule(); }
  }
  signal.addEventListener("abort", stop, { once: true });
  schedule();
  return stop;
}

export function createBrowserTransport(fetcher: typeof fetch = fetch): AnalyzeTransport {
  return async (file, id, signal, onPhase) => {
    const stopPolling = pollStatus(id, signal, onPhase, fetcher);
    const form = new FormData();
    form.append("file", file);
    try {
      let response: Response;
      try { response = await fetcher("/api/analyze", { method: "POST", body: form, signal, headers: { "X-Request-ID": id }, cache: "no-store" }); }
      catch { throw new AnalysisFailure(signal.aborted ? "ANALYSIS_TIMEOUT" : "UPSTREAM_UNAVAILABLE"); }
      if (signal.aborted) throw new AnalysisFailure("ANALYSIS_TIMEOUT");
      if (response.headers.get("X-Request-ID") !== id || !isJsonMediaType(response.headers.get("Content-Type"))) throw new AnalysisFailure("UPSTREAM_INVALID_RESPONSE");
      let data: unknown;
      try { data = await response.json(); } catch { throw new AnalysisFailure("UPSTREAM_INVALID_RESPONSE"); }
      if (signal.aborted) throw new AnalysisFailure("ANALYSIS_TIMEOUT");
      if (response.status === 200 && isSuccess(data)) return data;
      if (isError(data) && data.request_id === id && response.status === policy.errors[data.error.code].http) throw new AnalysisFailure(data.error.code);
      throw new AnalysisFailure("UPSTREAM_INVALID_RESPONSE");
    } finally { stopPolling(); }
  };
}
