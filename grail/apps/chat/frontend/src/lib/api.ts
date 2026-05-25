const TOKEN_KEY = "grail_token";

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function headers(): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) {
    h["Authorization"] = `Bearer ${token}`;
  }
  return h;
}

function extractDetail(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const d = (body as Record<string, unknown>).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length > 0) {
    const first = d[0];
    if (typeof first === "object" && first && "msg" in first) {
      return String((first as Record<string, unknown>).msg);
    }
    return String(first);
  }
  return "";
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = extractDetail(body) || `Request failed with status ${res.status}`;
    throw new ApiError(msg, res.status);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json();
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, { headers: headers() });
  return handleResponse<T>(res);
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(body),
  });
  return handleResponse<T>(res);
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "DELETE",
    headers: headers(),
  });
  return handleResponse<T>(res);
}

async function stream(
  path: string,
  body: unknown,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(
      err.detail || `Stream failed with status ${res.status}`,
      res.status,
    );
  }
  if (!res.body) {
    throw new ApiError("Response body is null", 500);
  }
  return res.body.getReader();
}

export interface SSEEvent {
  event: string;
  data: string;
}

export async function* parseSSE(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";
  let currentData = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    // Keep the last potentially incomplete line in the buffer
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData = line.slice(6);
      } else if (line === "" && currentEvent) {
        yield { event: currentEvent, data: currentData };
        currentEvent = "";
        currentData = "";
      }
    }
  }

  // Flush remaining
  if (currentEvent && currentData) {
    yield { event: currentEvent, data: currentData };
  }
}

export const api = {
  get,
  post,
  patch,
  delete: del,
  stream,
  setToken,
  getToken,
  clearToken,
};
