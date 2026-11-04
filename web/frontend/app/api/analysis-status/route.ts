import { statusProxy } from "@/lib/proxy";
import { backendConfig } from "@/lib/server-config";
export const runtime = "nodejs";
export async function GET(request: Request) { return statusProxy(request, backendConfig()); }
