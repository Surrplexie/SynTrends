/** SDK-level exceptions mapped from HTTP status codes — mirrors errors.py. */

export class SynTrendsAPIError extends Error {
  readonly statusCode: number;
  readonly detail: string;

  constructor(statusCode: number, detail: string) {
    super(`HTTP ${statusCode}: ${detail}`);
    this.name = "SynTrendsAPIError";
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

/** 401 — missing or invalid API key. */
export class AuthenticationError extends SynTrendsAPIError {
  constructor(statusCode: number, detail: string) {
    super(statusCode, detail);
    this.name = "AuthenticationError";
  }
}

/** 403 — a 3rdPS (read-only) key attempted a write. */
export class ForbiddenError extends SynTrendsAPIError {
  constructor(statusCode: number, detail: string) {
    super(statusCode, detail);
    this.name = "ForbiddenError";
  }
}

/** 404 — unknown route. */
export class NotFoundError extends SynTrendsAPIError {
  constructor(statusCode: number, detail: string) {
    super(statusCode, detail);
    this.name = "NotFoundError";
  }
}

/** 429 — 3rdPS key exceeded its request budget. */
export class RateLimitedError extends SynTrendsAPIError {
  constructor(statusCode: number, detail: string) {
    super(statusCode, detail);
    this.name = "RateLimitedError";
  }
}

export function raiseForStatus(status: number, bodyText: string): never | void {
  if (status < 400) return;
  let detail = bodyText;
  try {
    const parsed = JSON.parse(bodyText);
    if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
  } catch {
    // body wasn't JSON — use raw text
  }
  if (status === 401) throw new AuthenticationError(status, detail);
  if (status === 403) throw new ForbiddenError(status, detail);
  if (status === 404) throw new NotFoundError(status, detail);
  if (status === 429) throw new RateLimitedError(status, detail);
  throw new SynTrendsAPIError(status, detail);
}
