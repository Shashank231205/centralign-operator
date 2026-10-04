import type { NextRequest } from "next/server";

import { operatorApiKey, operatorApiUrl } from "@/lib/server-config";

// Backend-for-frontend proxy: the browser talks only to this origin, and the API key is added
// here on the server. Responses (including SSE streams and evidence files) are streamed through.
const FORWARDED_REQUEST_HEADERS = ["content-type", "idempotency-key", "last-event-id", "accept"];
const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "content-disposition",
  "cache-control",
  "retry-after",
];

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const target = new URL(`${operatorApiUrl()}/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;

  const headers = new Headers({ "X-API-Key": operatorApiKey() });
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" ? undefined : await request.text(),
    cache: "no-store",
    signal: request.signal,
  });

  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const dynamic = "force-dynamic";
