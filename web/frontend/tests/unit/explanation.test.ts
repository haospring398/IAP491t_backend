import { test } from "node:test";
import assert from "node:assert/strict";
import { factorCatalogue, isSuccess, validateFactors } from "../../lib/contracts";
import { directionText, factorText, strengthText } from "../../lib/explanation";
const factor = { factor: "num_attachments", direction: "positive", strength: 1 } as const;
const success = (explanation: unknown) => ({ analysis_status: "completed", label: "phishing", explanation });
test("explanations accept catalogued factors and reject unknown, duplicate, oversized or extra data", () => {
  assert(isSuccess(success({ factors: [factor, { factor: "text_content", direction: "negative", strength: 0.4 }] })));
  for (const explanation of [{ factors: [] }, { factors: Array(6).fill(factor) }, { factors: [{ ...factor, factor: "unknown_feature" }] },
    { factors: [factor, factor] }, { factors: [{ ...factor, strength: 0 }] }, { factors: [{ ...factor, strength: 1.2 }] },
    { factors: [{ ...factor, direction: "up" }] }, { factors: [{ ...factor, value: 3 }] }, { factors: [factor], score: 1 }, null]) {
    assert(!isSuccess(success(explanation)), JSON.stringify(explanation));
  }
});
test("catalogue validation and display copy follow the experience rules", () => {
  validateFactors({ version: 1, factors: factorCatalogue });
  for (const bad of [{ version: 2, factors: factorCatalogue }, { version: 1, factors: {} }, { version: 1, factors: { "Bad-Id": { label: "x" } } },
    { version: 1, factors: { ok: { label: "" } } }, { version: 1, factors: { ok: { label: "x", extra: "y" } } }, { version: 1, factors: factorCatalogue, extra: 1 }, null,
    { version: true, factors: factorCatalogue }, { version: 1, factors: { ok: { label: " x" } } }, { version: 1, factors: { ok: { label: "x " } } },
    { version: 1, factors: { ok: { label: "x".repeat(81) } } }]) {
    assert.throws(() => validateFactors(bad), /catalogue/);
  }
  assert.equal(factorText(factor).note, "Known dataset bias");
  assert.equal(factorText({ ...factor, factor: "text_content" }).label, "Overall wording (text model)");
  assert.equal(directionText(factor), "Toward Phishing");
  assert.equal(directionText({ ...factor, direction: "negative" }), "Toward Legit");
  assert.deepEqual([1, 0.67, 0.66, 0.34, 0.33, 0.01].map(strengthText), ["Strong", "Strong", "Moderate", "Moderate", "Weak", "Weak"]);
});
