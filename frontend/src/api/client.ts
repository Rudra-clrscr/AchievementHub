const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: string;
}

export interface AchievementRecord {
  status: "pending" | "approved" | "rejected";
  submitted_at: string;
  file_url: string;
  verified_by: number | null;
  verified_at: string | null;
  [key: string]: unknown;
}

export interface UploadResult {
  file_url: string;
  original_size: number;
  stored_size: number;
  content_type: string;
}

export type UploadCategory = "certificates" | "publications" | "patents" | "internships" | "events";

export async function uploadFile(token: string, category: UploadCategory, file: File): Promise<UploadResult> {
  const body = new FormData();
  body.append("category", category);
  body.append("file", file);

  const res = await fetch(`${API_BASE}/uploads`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body,
  });
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, errBody.detail ?? "Upload failed");
  }
  return res.json() as Promise<UploadResult>;
}

export function absoluteFileUrl(fileUrl: string): string {
  return fileUrl.startsWith("/") ? `${API_BASE}${fileUrl}` : fileUrl;
}

export function makeAchievementApi(basePath: string) {
  return {
    submit: (token: string, payload: Record<string, unknown>) =>
      request<AchievementRecord>(basePath, { method: "POST", body: JSON.stringify(payload) }, token),
    mine: (token: string) => request<AchievementRecord[]>(`${basePath}/mine`, {}, token),
    pending: (token: string) => request<AchievementRecord[]>(`${basePath}/pending`, {}, token),
    verify: (token: string, id: number, approve: boolean) =>
      request<AchievementRecord>(
        `${basePath}/${id}/verify`,
        { method: "PATCH", body: JSON.stringify({ approve }) },
        token
      ),
  };
}

export const certificatesApi = makeAchievementApi("/certificates");
export const publicationsApi = makeAchievementApi("/publications");
export const patentsApi = makeAchievementApi("/patents");
export const internshipsApi = makeAchievementApi("/internships");
export const eventsApi = makeAchievementApi("/events");

export interface MeResponse {
  id: number;
  name: string;
  email: string;
  role: string;
}

export interface Department {
  dept_id: number;
  dept_name: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  student_type: "inhouse" | "outhouse";
  department_id?: number;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  register: (payload: RegisterPayload) =>
    request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),

  departments: () => request<Department[]>("/departments"),

  me: (token: string) => request<MeResponse>("/auth/me", {}, token),
};
