import { readFile, writeFile } from "node:fs/promises";
import { compile } from "json-schema-to-typescript";
const schema = JSON.parse(await readFile(new URL("../../contracts/analysis.schema.json", import.meta.url), "utf8"));
const policy = JSON.parse(await readFile(new URL("../../contracts/transport-policy.schema.json", import.meta.url), "utf8"));
const banner = "/* Generated from contracts/*.schema.json. Do not edit. */";
const generated = (await compile(schema, "AnalysisContract", { bannerComment: banner })) + "\n" +
  (await compile(policy, "TransportPolicy", { bannerComment: banner }));
const target = new URL("../lib/contracts.generated.ts", import.meta.url);
if (process.argv.includes("--check")) {
  if (await readFile(target, "utf8") !== generated) throw new Error("Generated contract types are stale. Run npm run contracts:generate.");
} else await writeFile(target, generated);
