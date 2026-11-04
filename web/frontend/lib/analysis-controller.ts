import { AnalysisFailure, createBrowserTransport, type AnalyzeTransport, type Phase } from "./client";
import { policy, type AnalysisSuccess, type ErrorCode } from "./contracts";
type Base = { file: File | null; retries: number; retryAt: number };
export type AnalysisState = Base & (
  { state: "no-file" } |
  { state: "file-selected" } |
  { state: "analyzing"; requestId: string; filename: string; phase: Phase } |
  { state: "success"; filename: string; label: AnalysisSuccess["label"]; explanation?: AnalysisSuccess["explanation"] } |
  { state: "error"; code: ErrorCode }
);
const initial: AnalysisState = { state: "no-file", file: null, retries: 0, retryAt: 0 };
export function selectionError(files: readonly File[]): ErrorCode | null {
  if (files.length !== 1 || !/\.eml$/i.test(files[0].name)) return "INVALID_REQUEST";
  if (files[0].size === 0) return "EMPTY_EMAIL";
  if (files[0].size > policy.limits.fileBytes) return "EMAIL_TOO_LARGE";
  return null;
}
export function canStart(state: AnalysisState, now = Date.now()) {
  if (!state.file) return false;
  if (state.state === "file-selected") return true;
  return state.state === "error" && policy.errors[state.code].retryAfterSeconds > 0 && state.retries < policy.retry.maxRetries && now >= state.retryAt;
}
export function retryExplanation(state: AnalysisState, now = Date.now()) {
  if (state.state !== "error" || !state.file) return "";
  if (state.retries >= policy.retry.maxRetries) return "Retry limit reached for this file. Choose another file.";
  const remaining = Math.ceil((state.retryAt - now) / 1000);
  return remaining > 0 ? `Retry is available in ${remaining} seconds.` : `${policy.retry.maxRetries - state.retries} ${policy.retry.maxRetries - state.retries === 1 ? "retry" : "retries"} remaining for this file.`;
}

export class AnalysisController {
  private snapshot: AnalysisState = initial;
  private listeners = new Set<() => void>();
  private current: { id: string; abort: AbortController; timer: ReturnType<typeof setTimeout> } | null = null;
  constructor(private transport: AnalyzeTransport = createBrowserTransport(), private now = () => Date.now(), private uuid = () => crypto.randomUUID()) {}
  getSnapshot = () => this.snapshot;
  getServerSnapshot = () => initial;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private set(state: AnalysisState) { this.snapshot = state; this.listeners.forEach(listener => listener()); }
  select(files: readonly File[]) {
    if (this.current) return;
    // A cancelled picker does not invalidate an existing result/selection.
    if (files.length === 0) return;
    const error = selectionError(files);
    this.set(error ? { ...initial, state: "error", code: error } : { ...initial, state: "file-selected", file: files[0] });
  }
  remove() { if (!this.current) this.set(initial); }
  dispose() {
    if (this.current) { clearTimeout(this.current.timer); this.current.abort.abort(); this.current = null; }
  }
  start() {
    const state = this.snapshot;
    if (this.current || !canStart(state, this.now()) || !state.file) return false;
    const file = state.file;
    const id = this.uuid();
    const abort = new AbortController();
    const retries = state.state === "error" ? state.retries + 1 : 0;
    const timer = setTimeout(() => {
      if (this.current?.id !== id) return;
      abort.abort(); this.finishError(id, "ANALYSIS_TIMEOUT", file, retries);
    }, policy.deadlines.browserMs);
    this.current = { id, abort, timer };
    this.set({ state: "analyzing", file, retries, retryAt: 0, requestId: id, filename: file.name, phase: "unknown" });
    void this.transport(file, id, abort.signal, phase => {
      if (this.current?.id === id && this.snapshot.state === "analyzing") this.set({ ...this.snapshot, phase });
    }).then(result => {
      if (this.current?.id !== id) return;
      clearTimeout(timer); this.current = null;
      this.set({ state: "success", file, retries: 0, retryAt: 0, filename: file.name, label: result.label, ...(result.explanation && { explanation: result.explanation }) });
    }).catch(error => { this.finishError(id, error instanceof AnalysisFailure ? error.code : "INTERNAL_ERROR", file, retries); });
    return true;
  }
  private finishError(id: string, code: ErrorCode, file: File, retries: number) {
    if (this.current?.id !== id) return;
    clearTimeout(this.current.timer); this.current = null;
    const delay = policy.errors[code].retryAfterSeconds;
    this.set({ state: "error", code, file: delay ? file : null, retries, retryAt: this.now() + delay * 1000 });
  }
}
