import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveBackendConfig } from "../../lib/backend-config";
test("backend config accepts HTTPS and explicit local loopback only", () => {
  for (const url of ["https://ml.example.test", "http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"]) assert.equal(resolveBackendConfig(url, "sample-token")?.token, "sample-token");
  for (const url of [undefined, "", "not a URL", "http://ml.example.test", "ftp://ml.example.test", "https://user:secret@ml.example.test", "https://ml.example.test?secret=x", "https://ml.example.test#secret"]) assert.equal(resolveBackendConfig(url, "sample-token"), null);
});
test("backend config rejects missing, whitespace, control and unsafe header tokens", () => {
  for (const token of [undefined, "", " ", "token\r\nsecret", "token\tsecret", "token\u0000", "non-ascii-\u0100"]) assert.equal(resolveBackendConfig("https://ml.example.test", token), null);
});
