import "server-only";
import { resolveBackendConfig } from "./backend-config";
import type { ProxyConfig } from "./proxy";
export function backendConfig(): ProxyConfig {
  return resolveBackendConfig(process.env.ML_API_URL, process.env.ML_API_TOKEN);
}
