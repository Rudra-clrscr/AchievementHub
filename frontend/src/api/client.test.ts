import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  achievementsApi,
  absoluteFileUrl,
  api,
  ApiError,
  employeesApi,
  feedApi,
  uploadFile,
} from "./client";

const API_BASE = "http://api.test";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  } as unknown as Response;
}

function errorResponse(status: number, body: unknown, statusText = "Server Error") {
  return {
    ok: false,
    status,
    statusText,
    json: async () => body,
  } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function lastCall() {
  return fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
}

describe("request", () => {
  it("prefixes the configured API base", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await api.departments();

    expect(lastCall()[0]).toBe(`${API_BASE}/departments`);
  });

  it("attaches a bearer token when one is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1 }));

    await api.me("tok-123");

    expect(lastCall()[1].headers.Authorization).toBe("Bearer tok-123");
  });

  it("sends no Authorization header on public endpoints", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await api.departments();

    expect(lastCall()[1].headers).not.toHaveProperty("Authorization");
  });

  it("raises an ApiError carrying the status and the server's detail", async () => {
    fetchMock.mockResolvedValue(errorResponse(403, { detail: "Admin access only" }));

    const failure = await api.me("tok").catch((e) => e);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.status).toBe(403);
    expect(failure.message).toBe("Admin access only");
  });

  it("falls back to the status text when the error body is not JSON", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response);

    const failure = await api.me("tok").catch((e) => e);

    expect(failure.status).toBe(502);
    expect(failure.message).toBe("Bad Gateway");
  });

  it("returns undefined for a 204 instead of trying to parse a body", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 204,
      statusText: "",
      json: async () => {
        throw new Error("204 has no body");
      },
    } as unknown as Response);

    await expect(employeesApi.reject("tok", 7)).resolves.toBeUndefined();
  });
});

describe("cold-start retries", () => {
  // The free-tier backend spins down when idle. While it boots, fetch() throws
  // at the network level rather than returning an HTTP error, which the browser
  // surfaces as a CORS block because there is no response to carry the headers.
  // Retrying rides that out; the tests below pin both halves of the rule.

  it("retries a network-level failure and returns the eventual success", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue(jsonResponse([{ dept_id: 1, dept_name: "CSE" }]));

    const pending = api.departments();
    await vi.advanceTimersByTimeAsync(1000 + 3000);

    await expect(pending).resolves.toEqual([{ dept_id: 1, dept_name: "CSE" }]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does not retry a genuine HTTP error", async () => {
    // Retrying a 401 or a 422 cannot change the answer, and would quietly
    // multiply every failed login into five requests.
    fetchMock.mockResolvedValue(errorResponse(401, { detail: "Invalid email or password" }));

    await expect(api.login("a@example.com", "wrong")).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("gives up after the last backoff step and rethrows", async () => {
    vi.useFakeTimers();
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const pending = api.departments();
    const settled = pending.catch((e) => e);
    await vi.advanceTimersByTimeAsync(1000 + 3000 + 8000 + 15000);

    await expect(settled).resolves.toBeInstanceOf(TypeError);
    expect(fetchMock).toHaveBeenCalledTimes(5); // the first try plus four retries
  });
});

describe("uploadFile", () => {
  it("posts multipart form data without overriding the content type", async () => {
    // Setting Content-Type by hand here would omit the multipart boundary and
    // the backend would reject every upload. The browser must set it.
    fetchMock.mockResolvedValue(jsonResponse({ file_url: "https://cdn/x.jpg" }));
    const file = new File(["bytes"], "scan.png", { type: "image/png" });

    await uploadFile("tok", "certificates", file);

    const [url, init] = lastCall();
    expect(url).toBe(`${API_BASE}/uploads`);
    expect(init.headers).toEqual({ Authorization: "Bearer tok" });
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("category")).toBe("certificates");
    expect((init.body as FormData).get("file")).toBe(file);
  });

  it("surfaces an upload failure as an ApiError", async () => {
    fetchMock.mockResolvedValue(errorResponse(502, { detail: "Storage upload failed" }));
    const file = new File(["bytes"], "scan.png", { type: "image/png" });

    const failure = await uploadFile("tok", "certificates", file).catch((e) => e);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.message).toBe("Storage upload failed");
  });
});

describe("absoluteFileUrl", () => {
  it("leaves an already-absolute storage URL alone", () => {
    expect(absoluteFileUrl("https://cdn.example.com/a.pdf")).toBe("https://cdn.example.com/a.pdf");
  });

  it("prefixes a server-relative path with the API base", () => {
    expect(absoluteFileUrl("/uploads/a.pdf")).toBe(`${API_BASE}/uploads/a.pdf`);
  });
});

describe("feedApi", () => {
  it("requests the bare endpoint when no filters are set", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await feedApi.getLatest();

    expect(lastCall()[0]).toBe(`${API_BASE}/feed/latest`);
  });

  it("builds a query string from the filters that are set", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await feedApi.getLatest({ search: "robotics", owner_type: "student" });

    const url = new URL(lastCall()[0]);
    expect(url.pathname).toBe("/feed/latest");
    expect(url.searchParams.get("search")).toBe("robotics");
    expect(url.searchParams.get("owner_type")).toBe("student");
    expect(url.searchParams.has("category")).toBe(false);
  });

  it("escapes values rather than concatenating them raw", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await feedApi.getLatest({ search: "a&b=c d" });

    expect(new URL(lastCall()[0]).searchParams.get("search")).toBe("a&b=c d");
  });
});

describe("achievementsApi", () => {
  it("fetches the verification queue", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await achievementsApi.pending("tok");

    expect(lastCall()[0]).toBe(`${API_BASE}/achievements/pending`);
  });

  it("fetches the caller's own review history", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await achievementsApi.reviewed("tok");

    expect(lastCall()[0]).toBe(`${API_BASE}/achievements/reviewed`);
    expect(lastCall()[1].headers.Authorization).toBe("Bearer tok");
  });

  it("passes a status filter through to the history endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await achievementsApi.reviewed("tok", "rejected");

    expect(lastCall()[0]).toBe(`${API_BASE}/achievements/reviewed?status=rejected`);
  });

  it("sends the verdict and remarks when reviewing", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1 }));

    await achievementsApi.verify("tok", 12, false, "Illegible scan");

    const [url, init] = lastCall();
    expect(url).toBe(`${API_BASE}/achievements/12/verify`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ approve: false, remarks: "Illegible scan" });
  });
});

describe("auth endpoints", () => {
  it("sends the pre-login role choice when one was made", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ requires_role_selection: false }));

    await api.login("prof@example.com", "pw", "hod");

    expect(JSON.parse(lastCall()[1].body)).toEqual({
      email: "prof@example.com",
      password: "pw",
      role: "hod",
    });
  });

  it("exchanges a pending token for a session at the chosen role", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ access_token: "t", role: "admin" }));

    await api.selectRole("pending-abc", "admin");

    expect(lastCall()[0]).toBe(`${API_BASE}/auth/select-role`);
    expect(JSON.parse(lastCall()[1].body)).toEqual({
      pending_token: "pending-abc",
      role: "admin",
    });
  });

  it("omits the year filter when listing all sections of a department", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await api.sections(3);

    expect(lastCall()[0]).toBe(`${API_BASE}/departments/3/sections`);
  });

  it("includes the year filter when one is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await api.sections(3, 2);

    expect(lastCall()[0]).toBe(`${API_BASE}/departments/3/sections?year=2`);
  });
});
