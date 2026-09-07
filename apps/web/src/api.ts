import type { CodexAnalysis } from "@policylens/contracts" with { "resolution-mode": "import" };

interface SessionBootstrap {
  csrf_token: string;
  mode: "localhost-browser";
}

export interface PolicyLensApi {
  getDashboard(): Promise<unknown>;
  listImports(): Promise<unknown>;
  getImport(importId: string): Promise<unknown>;
  importManual(value: unknown): Promise<unknown>;
  chooseAndImportPdf(authority: string): Promise<unknown>;
  reviewImport(importId: string, value: unknown): Promise<unknown>;
  listProducts(includeDrafts?: boolean): Promise<unknown>;
  getProduct(versionId: string): Promise<unknown>;
  listPolicies(): Promise<unknown>;
  createPolicy(value: unknown): Promise<unknown>;
  getPolicy(policyId: string): Promise<unknown>;
  listSources(): Promise<unknown>;
  compare(versionIds: string[]): Promise<unknown>;
  compareEvidence(versionIds: string[]): Promise<unknown>;
  getResearchDashboard(): Promise<unknown>;
  previewResearch(): Promise<unknown>;
  startResearch(previewHash: string): Promise<unknown>;
  listResearchRuns(): Promise<unknown>;
  getResearchRun(runId: string): Promise<unknown>;
  cancelResearch(runId: string): Promise<unknown>;
  listResearchProducts(includeDrafts?: boolean): Promise<unknown>;
  search(query: string): Promise<unknown>;
  previewCodex(versionIds: string[], evidenceIds?: string[]): Promise<unknown>;
  runCodex(preview: unknown): Promise<{ result: CodexAnalysis; cliVersion: string }>;
  cancelCodex(): Promise<{ cancelled: boolean }>;
  saveAnalysis(value: unknown): Promise<unknown>;
  updateAnalysisStatus(analysisId: string, status: "ACCEPTED_AS_NOTE" | "REJECTED"): Promise<unknown>;
  createBackup(password: string): Promise<unknown>;
  previewRestore(password: string): Promise<unknown>;
  commitRestore(token: string): Promise<unknown>;
  getSettings(): Promise<unknown>;
  copyDataDirectory(): Promise<{ copied: boolean }>;
  getRuntimeInfo(): Promise<unknown>;
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
    const value = await response.json() as { message?: string; detail?: string; code?: string };
    return value.message ?? value.detail ?? value.code ?? `本地服务请求失败（${response.status}）。`;
  } catch {
    return `本地服务请求失败（${response.status}）。`;
  }
}

async function rawRequest(route: string, init: RequestInit = {}, retrySession = true): Promise<Response> {
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

async function request<T>(route: string, init: RequestInit = {}): Promise<T> {
  const response = await rawRequest(route, init);
  return await response.json() as T;
}

function jsonBody(value: unknown, method = "POST"): RequestInit {
  return { method, body: JSON.stringify(value) };
}

async function chooseFile(accept: string): Promise<File | null> {
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

function downloadBlob(blob: Blob, fileName: string): void {
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

export const policyLens: PolicyLensApi = {
  getDashboard: () => request("/api/v1/dashboard"),
  listImports: () => request("/api/v1/imports"),
  getImport: (importId) => request(`/api/v1/imports/${encodeURIComponent(importId)}`),
  importManual: (value) => request("/api/v1/imports/manual", jsonBody(value)),
  chooseAndImportPdf: async (authority) => {
    const file = await chooseFile(".pdf,application/pdf");
    if (!file) return { cancelled: true };
    if (file.size > 10 * 1024 * 1024) throw new Error("PDF 超过首次交付的 10 MiB 上限。");
    const form = new FormData();
    form.set("authority", authority);
    form.set("file", file, file.name);
    return await request("/api/v1/imports/pdf", { method: "POST", body: form });
  },
  reviewImport: (importId, value) => request(`/api/v1/imports/${encodeURIComponent(importId)}/review`, jsonBody(value)),
  listProducts: (includeDrafts = true) => request(`/api/v1/products?include_drafts=${includeDrafts ? "true" : "false"}`),
  getProduct: (versionId) => request(`/api/v1/products/${encodeURIComponent(versionId)}`),
  listPolicies: () => request("/api/v1/policies"),
  createPolicy: (value) => request("/api/v1/policies", jsonBody(value)),
  getPolicy: (policyId) => request(`/api/v1/policies/${encodeURIComponent(policyId)}`),
  listSources: () => request("/api/v1/sources"),
  compare: (versionIds) => request("/api/v1/comparisons/basic", jsonBody({ product_version_ids: versionIds })),
  compareEvidence: (versionIds) => request("/api/v1/comparisons/evidence", jsonBody({ product_version_ids: versionIds })),
  getResearchDashboard: () => request("/api/v1/research/dashboard"),
  previewResearch: () => request("/api/v1/research/preview", { method: "POST" }),
  startResearch: (previewHash) => request(
    "/api/v1/research/runs",
    jsonBody({ confirmed: true, preview_hash: previewHash })
  ),
  listResearchRuns: () => request("/api/v1/research/runs"),
  getResearchRun: (runId) => request(`/api/v1/research/runs/${encodeURIComponent(runId)}`),
  cancelResearch: (runId) => request(`/api/v1/research/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" }),
  listResearchProducts: (includeDrafts = true) => request(`/api/v1/research/products?include_drafts=${includeDrafts ? "true" : "false"}`),
  search: (query) => request(`/api/v1/search?q=${encodeURIComponent(query)}`),
  previewCodex: (versionIds, evidenceIds) => request(
    "/api/v1/codex/preview",
    jsonBody({ product_version_ids: versionIds, ...(evidenceIds ? { evidence_ids: evidenceIds } : {}) })
  ),
  runCodex: (preview) => request("/api/v1/codex/run", jsonBody({ confirmed: true, payload: preview })),
  cancelCodex: () => request("/api/v1/codex/cancel", { method: "POST" }),
  saveAnalysis: (value) => request("/api/v1/analyses", jsonBody(value)),
  updateAnalysisStatus: (analysisId, status) => request(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/status`,
    jsonBody({ status }, "PATCH")
  ),
  createBackup: async (password) => {
    const response = await rawRequest("/api/v1/backups/download", jsonBody({ password }));
    const fileName = response.headers.get("X-PolicyLens-Filename") ?? "PolicyLens-backup.plbackup";
    const payloadSha256 = response.headers.get("X-PolicyLens-Payload-SHA256") ?? "";
    downloadBlob(await response.blob(), fileName);
    return { file_name: fileName, payload_sha256: payloadSha256 };
  },
  previewRestore: async (password) => {
    const file = await chooseFile(".plbackup,application/octet-stream");
    if (!file) return { cancelled: true };
    const form = new FormData();
    form.set("password", password);
    form.set("file", file, file.name);
    return await request("/api/v1/restores/upload-preview", { method: "POST", body: form });
  },
  commitRestore: (token) => request("/api/v1/restores/commit", jsonBody({ restore_token: token })),
  getSettings: () => request("/api/v1/settings"),
  copyDataDirectory: async () => {
    const settings = await request<{ data_directory: string }>("/api/v1/settings");
    try {
      await navigator.clipboard.writeText(settings.data_directory);
    } catch {
      const field = document.createElement("textarea");
      field.value = settings.data_directory;
      field.style.position = "fixed";
      field.style.left = "-10000px";
      document.body.append(field);
      field.select();
      document.execCommand("copy");
      field.remove();
    }
    return { copied: true };
  },
  getRuntimeInfo: () => request("/api/v1/runtime")
};
