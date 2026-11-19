export type FieldType = "text" | "number" | "exists";
export type FieldSpec = { name: string; type: FieldType; description?: string };
export type JobStatus = "draft" | "active" | "healing" | "needs_human" | "paused";
export type Schedule = "manual" | "hourly" | "daily";
export type Job = {
  id: number;
  url: string;
  status: JobStatus;
  fields: FieldSpec[];
  schedule: Schedule | null;
  created_at: string;
};
export type FieldRule = {
  selector: string;
  type: FieldType;
  strip_prefix?: string | null;
};
export type Rules = { row_selector: string; fields: Record<string, FieldRule> };
export type Preview = {
  state: "pending" | "ready" | "failed";
  error: string | null;
  version_no: number | null;
  rules: Rules | null;
  row_count: number;
  rows: Record<string, unknown>[];
  warnings: string[];
};
export type RecordItem = {
  id: number;
  run_id: number;
  data: Record<string, unknown>;
  created_at: string;
};
export type RecordPage = { total: number; items: RecordItem[] };
export type CreateResult = { job_id: number; status: "draft" };
// "Run now" only queues the run (fetching a page is slow); the worker saves the rows.
export type RunQueued = { job_id: number; status: "queued" };

const baseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" && detail ? detail : `API request failed (HTTP ${status}).`);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    // Always read the latest job state, including immediately after approval or a run.
    response = await fetch(baseUrl + path, { ...options, cache: "no-store" });
  } catch (error) {
    if (options?.signal?.aborted) throw error;
    throw new Error("Could not reach the Mender API. Check that it is running and try again.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail);
  }

  return response.json().catch(() => {
    throw new Error("The Mender API returned an unreadable response.");
  });
}

export function apiPost<T>(path: string, body?: object): Promise<T> {
  if (body === undefined) return apiFetch<T>(path, { method: "POST" });

  return apiFetch<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function errorMessages(error: unknown): string[] {
  if (error instanceof ApiError && Array.isArray(error.detail)) {
    const messages = error.detail.flatMap((item) =>
      typeof item?.msg === "string" ? [item.msg] : [],
    );
    if (messages.length > 0) return messages;
  }

  return [error instanceof Error ? error.message : "Something went wrong. Try again."];
}
