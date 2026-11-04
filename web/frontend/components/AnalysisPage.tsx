"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AnalysisController, canStart, retryExplanation } from "@/lib/analysis-controller";
import { policy, type AnalysisSuccess } from "@/lib/contracts";
import { directionText, explanationHeading, explanationNotice, factorText, strengthText } from "@/lib/explanation";
import Icon from "./Icon";
const phaseCopy = { unknown: "Analyzing...", starting: "Starting analysis service...", receiving: "Sending email...", processing: "Analyzing email..." };
const labelCopy: Record<AnalysisSuccess["label"], string> = { legit: "Legit", spam_or_phishing: "Spam / phishing", phishing: "Phishing" };

export default function AnalysisPage() {
  const [controller] = useState(() => new AnalysisController());
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getServerSnapshot);
  const input = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLButtonElement>(null);
  const status = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const [now, setNow] = useState(0);
  const active = state.state === "analyzing";
  const retryNow = state.state === "error" ? Math.max(now, state.retryAt - policy.errors[state.code].retryAfterSeconds * 1000) : now;
  useEffect(() => () => controller.dispose(), [controller]);
  useEffect(() => {
    if (state.state !== "error" || !state.file || state.retries >= policy.retry.maxRetries) return;
    function tick() { const current = Date.now(); setNow(current); if (current >= state.retryAt) clearInterval(timer); }
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [state.state, state.file, state.retryAt, state.retries]);
  function openPicker() { if (!active && input.current) { input.current.value = ""; input.current.click(); } }
  function start() { if (controller.start()) status.current?.focus(); }
  return <main className="analysis-main" data-state={state.state}>
    <header className="page-intro"><h1>Email analysis</h1><p>Choose one email, then select Analyze.</p></header>
    <p className="privacy-note" role="note">Local demo model: phishing detection accuracy has not been independently established.</p>
    <section className="analyzer-card" aria-label="Email analyzer">
      <div className="analyzer-card-header"><Icon name="mail" /><h2>Choose an email</h2></div>
      <div className={`drop-zone${dragging && !active ? " is-dragging" : ""}`} onDragOver={event => { event.preventDefault(); if (!active) setDragging(true); }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }} onDrop={event => { event.preventDefault(); setDragging(false); if (!active) controller.select(Array.from(event.dataTransfer.files)); }}>
        <input ref={input} id="email-file" type="file" accept=".eml,message/rfc822" aria-label="Choose an EML file" aria-describedby="file-help" disabled={active} hidden onChange={event => controller.select(Array.from(event.target.files || []))} />
        <span className="upload-illustration"><Icon name="upload" size={32} /></span>
        <p className="drop-instruction">{dragging && !active ? "Release to select one .eml file" : "Drop one .eml file here"}</p>
        {state.file && <div className="file-summary"><p className="filename">{state.file.name}</p><p>{state.file.size.toLocaleString("en-US")} bytes</p></div>}
        <div className="file-controls"><button ref={picker} type="button" className="button button-secondary" aria-describedby="file-help" disabled={active} onClick={openPicker}>{state.file ? "Change file" : "Choose file"}</button>{state.file && <button type="button" className="button button-secondary" disabled={active} onClick={() => { controller.remove(); if (input.current) input.current.value = ""; picker.current?.focus(); }}>Remove file</button>}</div>
        <p id="file-help" className="meta">One .eml file. Maximum size: {policy.limits.fileBytes / 1024 / 1024} MiB, including attachments.</p>
      </div>
    </section>
    <p className="privacy-note">Selecting a file does not send it. Select Analyze to send this email to the analysis server.</p>
    <button type="button" className="button button-primary analyze-button" disabled={!canStart(state, now) || state.state === "error"} onClick={start}>{active ? "Analyzing..." : "Analyze"}</button>
    <div ref={status} className={`status-result-area${state.state === "error" ? " status-error" : ""}`} tabIndex={-1} aria-label="Analysis status" aria-busy={active}>
      {state.state !== "error" && <div role="status" aria-live="polite" aria-atomic="true">
        {state.state === "no-file" && <p>No file selected.</p>}
        {state.state === "file-selected" && <p>Ready to analyze.</p>}
        {state.state === "analyzing" && <p>{phaseCopy[state.phase]}</p>}
        {state.state === "success" && <><p>Analysis complete.</p><p className="filename">{state.filename}</p><p className="result-label">Result: {labelCopy[state.label]}</p></>}
      </div>}
      {state.state === "success" && state.explanation && <section className="explanation-list" aria-labelledby="explanation-heading">
        <h3 id="explanation-heading">{explanationHeading}</h3>
        <p className="meta">{explanationNotice}</p>
        <ol>{state.explanation.factors.map(factor => { const text = factorText(factor); return <li key={factor.factor}>
          <p><span className="factor-name">{text.label}</span>{text.note && <span className="meta"> ({text.note})</span>}</p>
          <p className="meta">{directionText(factor)} · {strengthText(factor.strength)}</p>
          <span className="factor-bar" aria-hidden="true"><span style={{ width: `${Math.max(4, factor.strength * 100)}%` }} /></span>
        </li>; })}</ol>
      </section>}
      {state.state === "error" && <><div role="alert"><p><strong>Analysis could not be completed.</strong></p><p>{policy.errors[state.code].message}</p></div><div className="recovery-actions">
        {state.file ? <><button type="button" className="button button-secondary" disabled={!canStart(state, retryNow)} onClick={start}>Retry</button><p className="meta">{retryExplanation(state, retryNow)}</p></> : <button type="button" className="button button-secondary" aria-describedby="file-help" onClick={openPicker}>Choose another file</button>}
      </div></>}
    </div>
  </main>;
}
