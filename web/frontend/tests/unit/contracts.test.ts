import { test } from "node:test";
import assert from "node:assert/strict";
import { isSuccess, isError, isStatus, isRequestId, policy, validatePolicy } from "../../lib/contracts";
const id = "672f0ea9-e237-45cd-8c08-8710f89b8258";
test("exact schemas accept declared release labels and reject aliases, extras and incomplete results", () => {
  for (const label of ["legit", "spam_or_phishing", "phishing"]) assert(isSuccess({ analysis_status: "completed", label }));
  for (const data of [{ label: "legit" }, { analysis_status: "pending", label: "legit" }, { analysis_status: "completed", label: "safe" }, { analysis_status: "completed", label: "Phishing" }, { analysis_status: "completed", label: "legit", score: 0.5 }, { isPhishing: true }]) assert(!isSuccess(data));
  assert(isError({ request_id: id, error: { code: "MODEL_UNAVAILABLE", message: "Unavailable" } }));
  assert(!isError({ request_id: id, error: { code: "UNKNOWN", message: "Unavailable" } }));
  assert(!isError({ request_id: id, error: { code: "MODEL_UNAVAILABLE", message: "Unavailable", stack: "secret" } }));
  assert(isStatus({ request_id: id, phase: "processing" }));
  assert(!isStatus({ request_id: id, phase: "processing", label: "legit" }));
  assert(!isStatus({ request_id: id, phase: "completed" }));
});
test("UUID is v4 correlation and policy validates bounds and errors", () => {
  assert(isRequestId(id)); assert(!isRequestId(id.replace("45cd", "15cd")));
  assert(!isRequestId("not-an-id"));
  validatePolicy(policy);
  const invalid = structuredClone(policy); invalid.deadlines.browserMs = invalid.deadlines.proxyMs;
  assert.throws(() => validatePolicy(invalid));
  assert.throws(() => validatePolicy({ ...policy, limits: {} }));
});
test("recovery policy cannot make input errors retryable or operational failures permanent", () => {
  for (const [code, error] of Object.entries(policy.errors)) {
    const changed = structuredClone(policy);
    changed.errors[code as keyof typeof changed.errors].retryAfterSeconds = error.retryAfterSeconds === 0 ? 1 : 0;
    assert.throws(() => validatePolicy(changed), /recovery policy/);
  }
});
