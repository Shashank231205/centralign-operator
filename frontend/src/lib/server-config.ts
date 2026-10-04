import "server-only";

// Server-side configuration. Required values have no defaults: a missing one fails the request
// loudly instead of silently talking to the wrong backend.
function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable ${name}`);
  }
  return value;
}

export function operatorApiUrl(): string {
  return required("OPERATOR_API_URL").replace(/\/$/, "");
}

export function operatorApiKey(): string {
  return required("OPERATOR_API_KEY");
}
