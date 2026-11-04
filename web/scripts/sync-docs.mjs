import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const destination = path.join(repository, "web/docs");
const directories = [
  ["_bmad-output/specs/spec-iap-web-application", "spec"],
  ["_bmad-output/planning-artifacts/ux-designs/ux-PhishingEmailDetection-2026-10-05", "ux"],
  ["_bmad-output/planning-artifacts/architecture/architecture-PhishingEmailDetection-2026-10-05", "architecture"],
  ["_bmad-output/planning-artifacts/prds/prd-PhishingEmailDetection-2026-10-05", "prd"],
];
const files = new Map([
  [path.join(repository, "docs/IAP_Web_Application_Plan.md"), "IAP_Web_Application_Plan.md"],
  [path.join(repository, "AGENTS.md"), "PROJECT-CONTEXT.md"],
  [path.join(repository, "_bmad-output/implementation-artifacts/spec-integrate-zip-frontend.md"), "implementation/spec-integrate-zip-frontend.md"],
  [path.join(repository, "_bmad-output/implementation-artifacts/spec-local-real-model-demo.md"), "implementation/spec-local-real-model-demo.md"],
  [path.join(repository, "_bmad-output/implementation-artifacts/spec-move-backend-to-web.md"), "implementation/spec-move-backend-to-web.md"],
  [path.join(repository, "web/backend/README.md"), "backend/README.md"],
]);
const portable = value => value.split(path.sep).join("/");
const digest = value => createHash("sha256").update(value).digest("hex");
const folders = new Map();
async function collect(source, target) {
  folders.set(source, target);
  for (const entry of await readdir(source, { withFileTypes: true })) {
    const from = path.join(source, entry.name);
    const to = path.join(target, entry.name);
    if (entry.isDirectory()) await collect(from, to);
    else if (entry.isFile()) files.set(from, to);
  }
}
for (const [source, target] of directories) await collect(path.join(repository, source), target);
// Validate every source before writing any snapshot; standalone copies fail clearly.
const sources = await Promise.all([...files].map(async ([source, target]) => ({ source, target, bytes: await readFile(source) })));
function relocate(reference, source, target) {
  if (/^(?:[a-z][a-z\d+.-]*:|\/|#)/i.test(reference)) return reference;
  const [pathname, anchor] = reference.split(/(?=#)/, 2);
  const from = path.resolve(path.dirname(source), decodeURI(pathname));
  let mapped = files.get(from) || folders.get(from);
  // Working review inputs contain excerpts whose links use the enclosing
  // document folder as their original base, rather than .working/ itself.
  if (!mapped && source.includes(`${path.sep}.working${path.sep}`)) {
    const enclosing = path.resolve(path.dirname(source), "..", decodeURI(pathname));
    mapped = files.get(enclosing) || folders.get(enclosing);
  }
  if (!mapped) return reference;
  const relative = portable(path.relative(path.dirname(target), mapped)) || ".";
  return relative + (pathname.endsWith("/") ? "/" : "") + (anchor || "");
}
const manifest = { snapshot: "web-development-handover", files: [] };
for (const { source, target, bytes } of sources) {
  let output = bytes;
  if (source.endsWith(".md")) {
    const text = bytes.toString("utf8")
      .replace(/(\]\()([^\s)]+)(\))/g, (_match, opening, reference, closing) => opening + relocate(reference, source, target) + closing)
      .replace(/^(\s*-\s+)([^\s]+)(\s*)$/gm, (_match, prefix, reference, suffix) => prefix + relocate(reference, source, target) + suffix);
    output = Buffer.from(text);
  }
  const outputPath = path.join(destination, target);
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, output);
  manifest.files.push({ source: portable(path.relative(repository, source)), snapshot: portable(target), sourceSha256: digest(bytes), snapshotSha256: digest(output) });
}
await writeFile(path.join(destination, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(`Refreshed ${sources.length} web handover documents.`);
