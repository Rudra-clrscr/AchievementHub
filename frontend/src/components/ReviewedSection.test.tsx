import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { achievementsApi, type ReviewedAchievement } from "../api/client";
import { ReviewedSection } from "./ReviewedSection";

function record(overrides: Partial<ReviewedAchievement> = {}): ReviewedAchievement {
  return {
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
    ...overrides,
  } as ReviewedAchievement;
}

let reviewed: MockInstance<typeof achievementsApi.reviewed>;

beforeEach(() => {
  reviewed = vi.spyOn(achievementsApi, "reviewed").mockResolvedValue([]);
});

describe("ReviewedSection", () => {
  it("loads the caller's history on mount", async () => {
    reviewed.mockResolvedValue([record()]);

    render(<ReviewedSection token="tok" isAdmin={false} />);

    expect(await screen.findByText("NPTEL Machine Learning")).toBeInTheDocument();
    expect(reviewed).toHaveBeenCalledWith("tok", undefined);
  });

  it("shows whose achievement each entry was", async () => {
    reviewed.mockResolvedValue([record({ owner_name: "Ada Student", category: "Certifications" })]);

    render(<ReviewedSection token="tok" isAdmin={false} />);

    expect(await screen.findByText(/Ada Student/)).toBeInTheDocument();
    expect(screen.getByText(/Certifications/)).toBeInTheDocument();
  });

  it("titles the panel for what the role actually did", async () => {
    // A coordinator verifies; an admin approves. Calling both "approved" would
    // misdescribe tier one.
    const { unmount } = render(<ReviewedSection token="tok" isAdmin={false} />);
    expect(await screen.findByText("Achievements You Verified")).toBeInTheDocument();
    unmount();

    render(<ReviewedSection token="tok" isAdmin />);
    expect(await screen.findByText("Achievements You Approved")).toBeInTheDocument();
  });

  it("refetches with a status filter when one is chosen", async () => {
    reviewed.mockResolvedValue([record()]);
    render(<ReviewedSection token="tok" isAdmin={false} />);
    await screen.findByText("NPTEL Machine Learning");

    await userEvent.click(screen.getByRole("button", { name: "Rejected" }));

    await waitFor(() => expect(reviewed).toHaveBeenLastCalledWith("tok", "rejected"));
  });

  it("goes back to the unfiltered request when All is chosen again", async () => {
    render(<ReviewedSection token="tok" isAdmin={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Approved" }));
    await waitFor(() => expect(reviewed).toHaveBeenLastCalledWith("tok", "approved"));

    await userEvent.click(screen.getByRole("button", { name: "All" }));

    await waitFor(() => expect(reviewed).toHaveBeenLastCalledWith("tok", undefined));
  });

  it("links to the stored proof file", async () => {
    reviewed.mockResolvedValue([record({ file_url: "https://cdn.example.com/proof.pdf" })]);

    render(<ReviewedSection token="tok" isAdmin={false} />);

    const link = await screen.findByRole("link", { name: "View file" });
    expect(link).toHaveAttribute("href", "https://cdn.example.com/proof.pdf");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("shows the remarks left on a rejection", async () => {
    reviewed.mockResolvedValue([
      record({ status: "rejected", metadata_fields: { remarks: "Certificate is illegible" } }),
    ]);

    render(<ReviewedSection token="tok" isAdmin={false} />);

    expect(await screen.findByText(/Certificate is illegible/)).toBeInTheDocument();
  });

  it("explains an empty history rather than showing a blank panel", async () => {
    reviewed.mockResolvedValue([]);

    render(<ReviewedSection token="tok" isAdmin={false} />);

    expect(await screen.findByText("You have not reviewed anything yet.")).toBeInTheDocument();
  });

  it("says which filter came back empty", async () => {
    render(<ReviewedSection token="tok" isAdmin={false} />);
    await screen.findByText("You have not reviewed anything yet.");

    await userEvent.click(screen.getByRole("button", { name: "Rejected" }));

    expect(
      await screen.findByText("Nothing you reviewed is currently rejected.")
    ).toBeInTheDocument();
  });

  it("surfaces a load failure instead of hanging on the spinner", async () => {
    reviewed.mockRejectedValue(new Error("Faculty, HOD, or admin access only"));

    render(<ReviewedSection token="tok" isAdmin={false} />);

    expect(await screen.findByText("Faculty, HOD, or admin access only")).toBeInTheDocument();
  });

  it("dates each entry by the decision the viewer made, not the submission", async () => {
    // A coordinator's list is ordered and dated by when they verified; an
    // admin's by when they approved. Showing submitted_at for both would make
    // the two lists indistinguishable.
    reviewed.mockResolvedValue([
      record({ verified_at: "2026-08-02T10:00:00Z", approved_at: "2026-12-25T10:00:00Z" }),
    ]);

    const { unmount } = render(<ReviewedSection token="tok" isAdmin={false} />);
    expect(await screen.findByText(new Date("2026-08-02T10:00:00Z").toLocaleDateString()))
      .toBeInTheDocument();
    unmount();

    render(<ReviewedSection token="tok" isAdmin />);
    expect(await screen.findByText(new Date("2026-12-25T10:00:00Z").toLocaleDateString()))
      .toBeInTheDocument();
  });
});
