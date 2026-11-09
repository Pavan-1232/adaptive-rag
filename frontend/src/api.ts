// Thin wrappers over the backend API. Same origin: "/api" is proxied in development and served
// by FastAPI in normal use.

export type KnowledgeBase = { id: number; name: string; allow_cloud: boolean; embedding_model: string };

export type Doc = {
  id: number;
  filename: string;
  format: string;
  status: string;
  error: string | null;
  warnings: string[];
  version: number;
};

export type Job = { id: number; status: string; error: string | null };

export type Citation = {
  id: string;
  document_id: number;
  filename: string;
  label: string;
  section_heading: string | null;
  snippet: string;
  passage: string;
  source: string;
};

export type Answer = {
  status: "answered" | "partial" | "insufficient";
  answer: string;
  citations: Citation[];
  warnings: string[];
  provider: string;
  trace_id: number;
  // What retrieval searched; differs from the question for a follow-up.
  searched_question?: string;
};

export type Provider = "ollama" | "openai" | "gemini" | "anthropic";
export type CloudProvider = Exclude<Provider, "ollama">;
export type KeySource = "keychain" | "env" | "not set";
export type KeySources = Record<CloudProvider, KeySource>;

export type Comparison = {
  name: string;
  metric: string;
  n: number;
  difference: number;
  ci_low: number;
  ci_high: number;
  verdict: string;
  note: string;
};

export type Evaluation = {
  dataset: string;
  baseline: {
    name: string;
    answerable: number;
    unanswerable: number;
    recall_at_budget: [number, number, number];
    hit_at_5: [number, number, number];
    reciprocal_rank: [number, number, number];
    unanswerable_refused: number;
    generation_p50_s: number;
  };
  comparisons: Comparison[];
  sources: string[];
};

export type Health = { status: "ok" | "degraded"; embedding_model: boolean; llm_model: boolean };

export class ApiError extends Error {}

// FastAPI returns {detail: string} for our errors and {detail: [...]} for validation errors.
function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "The request was not valid. Please check your input.";
  return `Request failed (HTTP ${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: init?.body ? { "content-type": "application/json" } : undefined,
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorMessage(response.status, body));
  return body as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/health"),
  listKbs: () => request<KnowledgeBase[]>("/kbs"),
  createKb: (name: string) => request<KnowledgeBase>("/kbs", json("POST", { name })),
  setCloud: (id: number, allow_cloud: boolean) =>
    request<KnowledgeBase>(`/kbs/${id}`, json("PATCH", { allow_cloud })),
  deleteKb: (id: number) => request<void>(`/kbs/${id}`, json("DELETE")),
  listDocs: (kbId: number) => request<Doc[]>(`/kbs/${kbId}/documents`),
  deleteDoc: (id: number) => request<void>(`/documents/${id}`, json("DELETE")),
  job: (id: number) => request<Job>(`/jobs/${id}`),
  // previousTraceId: the chat's previous turn in this knowledge base, for follow-ups.
  ask: (kbId: number, question: string, provider: Provider, previousTraceId?: number) =>
    request<Answer>(
      `/kbs/${kbId}/query`,
      json("POST", previousTraceId ? { question, provider, previous_trace_id: previousTraceId } : { question, provider }),
    ),
  keySources: () => request<KeySources>("/keys"),
  // The key goes straight into the request body; callers must not keep it anywhere.
  saveKey: (provider: CloudProvider, key: string) =>
    request<void>(`/keys/${provider}`, json("PUT", { key })),
  removeKey: (provider: CloudProvider) => request<void>(`/keys/${provider}`, json("DELETE")),
  evaluation: () => request<Evaluation>("/evaluation"),
};

export type UploadResult = { document: Doc; job_id: number | null; duplicate: boolean };

// XMLHttpRequest, because fetch has no upload progress events.
export function uploadFile(
  kbId: number,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/kbs/${kbId}/documents`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // not JSON: handled below
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as UploadResult);
      else reject(new ApiError(errorMessage(xhr.status, body)));
    };
    xhr.onerror = () => reject(new ApiError("The upload failed. Is the server running?"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const PROVIDER_NAMES: Record<Provider, string> = {
  ollama: "Ollama (local)",
  openai: "OpenAI",
  gemini: "Gemini",
  anthropic: "Anthropic",
};
