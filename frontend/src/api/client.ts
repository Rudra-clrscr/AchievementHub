const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8001";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// The backend free-tier host spins down when idle and cold-starts on the
// next request; while it's booting, requests fail at the network level
// (fetch() throws, there's no HTTP response at all) rather than with an
// HTTP error -- the browser reports this as a CORS block since there's no
// response to carry CORS headers, even though CORS itself is configured
// fine. Retrying rides out that boot window instead of surfacing it as a
// bare "failed" to the user. Only network-level failures are retried --
// a real HTTP error response (4xx/5xx) is returned immediately, not
// retried, since retrying wouldn't change a genuine error.
const RETRY_DELAYS_MS = [1000, 3000, 8000, 15000];

async function fetchWithRetry(input: string, init: RequestInit): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await fetch(input, init);
    } catch (err) {
      if (attempt >= RETRY_DELAYS_MS.length) throw err;
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
    }
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetchWithRetry(`${API_BASE}${path}`, { ...options, headers });
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

export interface LoginResult {
  requires_role_selection: boolean;
  access_token?: string;
  token_type?: string;
  role?: string;
  roles?: string[];
  pending_token?: string;
}

export interface AchievementRecord {
<<<<<<< Updated upstream
  status: "pending" | "verified" | "approved" | "rejected";
=======
  status: "pending" | "pending_hod" | "pending_admin" | "revision_required" | "approved" | "rejected";
>>>>>>> Stashed changes
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
  thumbnail_url?: string;
}

export type UploadCategory = "certificates" | "publications" | "patents" | "internships" | "events" | "achievements";

export async function uploadFile(token: string, category: UploadCategory, file: File): Promise<UploadResult> {
  const body = new FormData();
  body.append("category", category);
  body.append("file", file);

  const res = await fetchWithRetry(`${API_BASE}/uploads`, {
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
    verify: (token: string, id: number, approve: boolean, remarks?: string) =>
      request<AchievementRecord>(
        `${basePath}/${id}/verify`,
        { method: "PATCH", body: JSON.stringify({ approve, remarks }) },
        token
      ),
  };
}

export const achievementsApi = makeAchievementApi("/achievements");

export const STUDENT_CATEGORIES = [
  "Academic Achievements", "Research & Publications", "Intellectual Property",
  "Internship & Industrial Training", "Certifications", "Technical Competitions",
  "Project Achievements", "Event Participation", "Leadership & Club Activities",
  "Sports", "Cultural Activities", "Placement & Career", "Community Service", "Awards & Recognition"
];

export const FACULTY_CATEGORIES = [
  "Academic Achievements", "Research Publications", "Intellectual Property",
  "Grants & Funding", "Teaching & Learning", "Faculty Development",
  "Professional Memberships", "Administrative Responsibilities", "Student Mentorship",
  "Consultancy & Industry Collaboration", "Invited Talks", "Awards & Recognition",
  "Editorial & Review Activities", "Event Organization"
];

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

export interface AdminStudent {
  student_id: number;
  name: string;
  email: string;
  department_id: number | null;
  coordinator_id: number | null;
  coordinator_name: string | null;
}

export interface Coordinator {
  emp_id: number;
  name: string;
}

export const studentsApi = {
  list: (token: string) => request<AdminStudent[]>("/students", {}, token),
  coordinators: (token: string) => request<Coordinator[]>("/students/coordinators", {}, token),
  assignCoordinator: (token: string, studentId: number, coordinatorId: number) =>
    request<AdminStudent>(
      `/students/${studentId}/coordinator`,
      { method: "PATCH", body: JSON.stringify({ coordinator_id: coordinatorId }) },
      token
    ),
};

export interface AdminFaculty {
  emp_id: number;
  name: string;
  email: string;
  department_id: number | null;
  hod_id: number | null;
  hod_name: string | null;
}

export interface Hod {
  emp_id: number;
  name: string;
}

export const employeesApi = {
  listFaculty: (token: string) => request<AdminFaculty[]>("/employees/faculty", {}, token),
  listHods: (token: string) => request<Hod[]>("/employees/hods", {}, token),
  assignHod: (token: string, empId: number, hodId: number) =>
    request<AdminFaculty>(
      `/employees/${empId}/hod`,
      { method: "PATCH", body: JSON.stringify({ hod_id: hodId }) },
      token
    ),
};

export const api = {
  login: (email: string, password: string) =>
    request<LoginResult>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  selectRole: (pendingToken: string, role: string) =>
    request<LoginResult>("/auth/select-role", { method: "POST", body: JSON.stringify({ pending_token: pendingToken, role }) }),

  register: (payload: RegisterPayload) =>
    request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),

  departments: () => request<Department[]>("/departments"),

  me: (token: string) => request<MeResponse>("/auth/me", {}, token),
};

export interface UploadResponse {
  url: string;
  original_size: number;
  stored_size: number;
  content_type: string;
  thumbnail_url?: string;
}

export interface FeedItem {
  id: number;
  type: string;
  title: string;
  owner_type: string;
  student_name: string | null;
  category: string | null;
  verified_at: string | null;
  file_url: string;
  is_featured: boolean;
  thumbnail_url?: string;
}

export const feedApi = {
  getLatest: (params?: { search?: string; category?: string; owner_type?: string }) => {
    const query = new URLSearchParams();
    if (params?.search) query.append("search", params.search);
    if (params?.category) query.append("category", params.category);
    if (params?.owner_type) query.append("owner_type", params.owner_type);
    
    const queryString = query.toString();
    return request<FeedItem[]>(`/feed/latest${queryString ? `?${queryString}` : ""}`);
  },
  getTop: () => request<FeedItem[]>("/feed/top"),
};

