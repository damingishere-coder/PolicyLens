interface SessionBootstrap {
  csrf_token: string;
  mode: "localhost-browser";
}

let csrfToken = "";

let sessionPromise: Promise<void> | null = null;

async function ensureSession(): Promise<void> {
  if (csrfToken) return;
  sessionPromise ??= (async () => {
    const response = await fetch("/api/v1/session", {
      credentials: "same-origin",
      cache: "no-store"
    });
    if (!response.ok) throw new Error("无法建立本地安全会话。");
    const value = await response.json() as SessionBootstrap;
    if (value.mode !== "localhost-browser" || value.csrf_token.length < 32) {
      throw new Error("本地服务返回了无效的安全会话。");
    }
    csrfToken = value.csrf_token;
  })().finally(() => {
    sessionPromise = null;
  });
  await sessionPromise;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const value = await response.json() as { message?: string; detail?: unknown; code?: string };
    if (typeof value.message === "string") return value.message;
    if (typeof value.detail === "string") return value.detail;
    if (Array.isArray(value.detail)) return "填写的信息不符合要求，请检查金额、日期、必填项及文字长度。";
    return value.code ?? `本地服务请求失败（${response.status}）。`;
  } catch {
    return `本地服务请求失败（${response.status}）。`;
  }
}

export async function rawRequest(route: string, init: RequestInit = {}, retrySession = true): Promise<Response> {
  await ensureSession();
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!new Set(["GET", "HEAD", "OPTIONS"]).has(method)) {
    headers.set("X-PolicyLens-CSRF", csrfToken);
  }
  const response = await fetch(route, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store"
  });
  if (response.status === 401 && retrySession) {
    csrfToken = "";
    await ensureSession();
    return await rawRequest(route, init, false);
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  return response;
}

export async function request<T>(route: string, init: RequestInit = {}): Promise<T> {
  const response = await rawRequest(route, init);
  return await response.json() as T;
}

export function jsonBody(value: unknown, method = "POST"): RequestInit {
  return { method, body: JSON.stringify(value) };
}

export async function chooseFile(accept: string): Promise<File | null> {
  return await new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.tabIndex = -1;
    input.setAttribute("aria-hidden", "true");
    input.style.position = "fixed";
    input.style.left = "-10000px";
    document.body.append(input);
    let finished = false;
    const finish = (file: File | null) => {
      if (finished) return;
      finished = true;
      window.removeEventListener("focus", onFocus);
      input.remove();
      resolve(file);
    };
    const onFocus = () => window.setTimeout(() => finish(input.files?.[0] ?? null), 300);
    input.addEventListener("change", () => finish(input.files?.[0] ?? null), { once: true });
    window.addEventListener("focus", onFocus, { once: true });
    input.click();
  });
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
