import Ajv from "ajv";
import schema from "../../contracts/analysis.schema.json";
import policySchema from "../../contracts/transport-policy.schema.json";
import policyData from "../../contracts/transport-policy.json";
import factorData from "../../contracts/explanation-factors.json";
import type { AnalysisSuccess, AnalysisError, AnalysisStatus, Explanation, RequestId, TransportPolicy } from "./contracts.generated";
export type { AnalysisSuccess, AnalysisError, AnalysisStatus, Explanation, ExplanationFactor, RequestId } from "./contracts.generated";
export type ErrorCode = AnalysisError["error"]["code"];
export type FactorEntry = { label: string; note?: string };
const ajv = new Ajv({ strict: true, allErrors: false });
ajv.addSchema(schema);
const isSuccessShape = ajv.compile<AnalysisSuccess>({ $ref: "urn:iap:analysis:v1#/definitions/AnalysisSuccess" });
export function validateFactors(value: unknown): asserts value is { version: 1; factors: Record<string, FactorEntry> } {
  // Cùng quy tắc với validate_factors ở backend: ASCII in được, không có khoảng trắng đầu/cuối.
  const text = (entry: unknown) => typeof entry === "string" && /^[\x21-\x7e](?:[\x20-\x7e]{0,78}[\x21-\x7e])?$/.test(entry);
  const document = value as { version?: unknown; factors?: unknown };
  const entries = document && typeof document.factors === "object" && document.factors ? Object.entries(document.factors) : [];
  if (!document || Object.keys(document).sort().join() !== "factors,version" || document.version !== 1 || !entries.length ||
    !entries.every(([key, entry]) => /^[a-z][a-z0-9_]{0,63}$/.test(key) && typeof entry === "object" && entry !== null &&
      Object.keys(entry).every(name => name === "label" || name === "note") && text((entry as FactorEntry).label) &&
      (!("note" in entry) || text((entry as FactorEntry).note)))) throw new Error("Invalid explanation factor catalogue");
}
validateFactors(factorData);
export const factorCatalogue: Readonly<Record<string, FactorEntry>> = factorData.factors;
function catalogued(explanation: Explanation | undefined) {
  if (!explanation) return true;
  const ids = explanation.factors.map(item => item.factor);
  return new Set(ids).size === ids.length && ids.every(id => Object.hasOwn(factorCatalogue, id));
}
// Explanation phải đúng schema, chỉ dùng factor có trong catalogue và không lặp (AD-14).
export function isSuccess(data: unknown): data is AnalysisSuccess { return isSuccessShape(data) && catalogued(data.explanation); }
export const isError = ajv.compile<AnalysisError>({ $ref: "urn:iap:analysis:v1#/definitions/AnalysisError" });
export const isStatus = ajv.compile<AnalysisStatus>({ $ref: "urn:iap:analysis:v1#/definitions/AnalysisStatus" });
export const isRequestId = ajv.compile<RequestId>({ $ref: "urn:iap:analysis:v1#/definitions/RequestId" });
export function validatePolicy(value: unknown): asserts value is TransportPolicy {
  if (!ajv.validate(policySchema, value)) throw new Error("Invalid shared transport policy");
  const p = value as TransportPolicy;
  const inputCodes: ErrorCode[] = ["INVALID_REQUEST", "EMAIL_TOO_LARGE", "EMPTY_EMAIL", "INVALID_EMAIL", "INSUFFICIENT_CONTENT", "RESOURCE_LIMIT"];
  for (const [code, error] of Object.entries(p.errors)) {
    if (inputCodes.includes(code as ErrorCode) ? error.retryAfterSeconds !== 0 : error.retryAfterSeconds === 0) {
      throw new Error("Inconsistent shared recovery policy");
    }
  }
  if (!(p.limits.fileBytes < p.limits.multipartBytes &&
    p.deadlines.backendMs < p.deadlines.proxyMs && p.deadlines.proxyMs < p.deadlines.browserMs &&
    p.deadlines.backendReserveMs >= p.deadlines.clockSkewMs + p.deadlines.terminateMs + p.deadlines.killReapMs)) {
    throw new Error("Inconsistent shared transport policy");
  }
}
validatePolicy(policyData);
export const policy: Readonly<TransportPolicy> = policyData;
export function errorEnvelope(code: ErrorCode, requestId: string): AnalysisError {
  return { error: { code, message: policy.errors[code].message }, request_id: requestId };
}
export function isCorrelated(header: string | null, requestId: string): boolean { return header === requestId; }
export function isJsonMediaType(value: string | null): boolean { return /^application\/json(?:\s*;|$)/i.test(value || ""); }
