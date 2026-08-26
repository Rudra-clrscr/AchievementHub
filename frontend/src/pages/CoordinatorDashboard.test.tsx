import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { achievementsApi, api } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { CoordinatorDashboard } from "./CoordinatorDashboard";

const STORAGE_KEY = "achievementhub_session";

/** Every role that the /coordinator route admits. */
const VERIFIER_ROLES = ["faculty", "hod", "admin"] as const;

function renderAs(role: string) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ token: "tok", role }));
  return render(
    <MemoryRouter>
      <AuthProvider>
        <CoordinatorDashboard />
      </AuthProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.spyOn(api, "me").mockResolvedValue({
    id: 1,
    name: "Test User",
    email: "user@example.com",
    role: "faculty",
  });
  vi.spyOn(achievementsApi, "pending").mockResolvedValue([]);
  vi.spyOn(achievementsApi, "reviewed").mockResolvedValue([]);
  vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([]);
});

describe("Review History availability", () => {
  it.each(VERIFIER_ROLES)("is offered in the sidebar to %s", async (role) => {
    renderAs(role);

    expect(await screen.findByRole("button", { name: "Review History" })).toBeInTheDocument();
  });

  it.each(VERIFIER_ROLES)("opens a working history panel for %s", async (role) => {
    renderAs(role);

    await userEvent.click(await screen.findByRole("button", { name: "Review History" }));

    // The panel rendered and actually asked the backend for this user's history.
    expect(achievementsApi.reviewed).toHaveBeenCalledWith("tok", undefined);
    expect(
      await screen.findByRole("heading", { name: /Achievements You (Verified|Approved)/ })
    ).toBeInTheDocument();
  });

  it.each(VERIFIER_ROLES)("lets %s open the proof file of a record they reviewed", async (role) => {
    vi.spyOn(achievementsApi, "reviewed").mockResolvedValue([
      {
        id: 1,
        title: "NPTEL Machine Learning",
        category: "Certifications",
        sub_category: null,
        owner_name: "Ada Student",
        status: "approved",
        submitted_at: "2026-08-01T10:00:00Z",
        file_url: "https://cdn.example.com/proof.pdf",
        verified_by: 5,
        verified_at: "2026-08-02T10:00:00Z",
        approved_by: 9,
        approved_at: "2026-08-03T10:00:00Z",
        metadata_fields: null,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any,
    ]);
    renderAs(role);

    await userEvent.click(await screen.findByRole("button", { name: "Review History" }));

    const link = await screen.findByRole("link", { name: "View file" });
    expect(link).toHaveAttribute("href", "https://cdn.example.com/proof.pdf");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("labels the panel for the tier each role actually acts at", async () => {
    const { unmount } = renderAs("faculty");
    await userEvent.click(await screen.findByRole("button", { name: "Review History" }));
    expect(
      await screen.findByRole("heading", { name: "Achievements You Verified" })
    ).toBeInTheDocument();
    unmount();

    const hod = renderAs("hod");
    await userEvent.click(await screen.findByRole("button", { name: "Review History" }));
    expect(
      await screen.findByRole("heading", { name: "Achievements You Verified" })
    ).toBeInTheDocument();
    hod.unmount();

    renderAs("admin");
    await userEvent.click(await screen.findByRole("button", { name: "Review History" }));
    expect(
      await screen.findByRole("heading", { name: "Achievements You Approved" })
    ).toBeInTheDocument();
  });
});

describe("Roster availability", () => {
  const ROSTER_LABEL: Record<string, string> = {
    faculty: "My Students",
    hod: "My Faculty",
    admin: "Department Roster",
  };

  it.each(VERIFIER_ROLES)("names the roster for what %s is responsible for", async (role) => {
    renderAs(role);

    expect(
      await screen.findByRole("button", { name: ROSTER_LABEL[role] })
    ).toBeInTheDocument();
  });

  it.each(VERIFIER_ROLES)("opens a working roster panel for %s", async (role) => {
    renderAs(role);

    await userEvent.click(await screen.findByRole("button", { name: ROSTER_LABEL[role] }));

    expect(achievementsApi.byOwner).toHaveBeenCalledWith("tok");
    expect(
      await screen.findByRole("heading", { name: ROSTER_LABEL[role] })
    ).toBeInTheDocument();
  });
});

describe("sidebar scoping still holds", () => {
  it.each(["faculty", "hod"] as const)(
    "does not offer %s the admin-only sections",
    async (role) => {
      renderAs(role);
      await screen.findByRole("button", { name: "Review History" });

      expect(screen.queryByRole("button", { name: "Students" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Faculty" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Registrations" })).not.toBeInTheDocument();
    }
  );

  it("still offers admin the admin-only sections alongside the history", async () => {
    renderAs("admin");

    expect(await screen.findByRole("button", { name: "Review History" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Students" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Faculty" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrations" })).toBeInTheDocument();
  });

  it("keeps the verification queue as the landing view", async () => {
    renderAs("faculty");

    // The pending queue panel is what renders first; the history panel is not
    // mounted until its sidebar entry is chosen.
    expect(await screen.findByRole("heading", { name: /Pending/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Achievements You/ })).not.toBeInTheDocument();
  });
});
