import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { achievementsApi, type OwnerAchievements } from "../api/client";
import { RosterSection, rosterTitle } from "./RosterSection";

/** The roster is a second doorway onto the verification queue, so the two
 * things worth pinning are that it groups records under the right person and
 * that deciding from here goes through the same `verify` call the queue uses
 * -- a divergence there would mean two workflows that can drift apart. */

function record(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    title: "NPTEL Machine Learning",
    category: "Certifications",
    sub_category: null,
    status: "pending",
    submitted_at: "2026-08-01T10:00:00Z",
    file_url: "https://cdn.example.com/proof.pdf",
    verified_by: null,
    verified_at: null,
    approved_by: null,
    approved_at: null,
    metadata_fields: null,
    ...over,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any;
}

function owner(over: Partial<OwnerAchievements> = {}): OwnerAchievements {
  return {
    owner_id: 7,
    owner_type: "student",
    name: "Ada Student",
    email: "ada@example.com",
    approved: [],
    pending: [],
    ...over,
  };
}

beforeEach(() => {
  vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([]);
  vi.spyOn(achievementsApi, "verify").mockResolvedValue(record({ status: "verified" }));
});

describe("roster labelling", () => {
  it("names the roster after who the role is responsible for", () => {
    expect(rosterTitle("faculty")).toBe("My Students");
    expect(rosterTitle("hod")).toBe("My Faculty");
    expect(rosterTitle("admin")).toBe("Department Roster");
  });
});

describe("grouping by person", () => {
  it("lists each person with their approved and awaiting counts", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([
      owner({
        approved: [record({ id: 1, status: "approved" }), record({ id: 2, status: "approved" })],
        pending: [record({ id: 3 })],
      }),
      owner({ owner_id: 8, name: "Grace Student", email: "grace@example.com" }),
    ]);

    render(<RosterSection token="tok" role="faculty" />);

    expect(await screen.findByText("Ada Student")).toBeInTheDocument();
    expect(screen.getByText("Grace Student")).toBeInTheDocument();
    expect(screen.getByText("2 approved")).toBeInTheDocument();
    expect(screen.getByText("1 to verify")).toBeInTheDocument();
  });

  it("shows a person's approved achievements only once expanded", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([
      owner({ approved: [record({ id: 1, title: "Hackathon Winner", status: "approved" })] }),
    ]);

    render(<RosterSection token="tok" role="faculty" />);

    expect(screen.queryByText("Hackathon Winner")).not.toBeInTheDocument();

    await userEvent.click(await screen.findByText("Ada Student"));

    expect(screen.getByText("Hackathon Winner")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View file" })).toHaveAttribute(
      "href",
      "https://cdn.example.com/proof.pdf"
    );
  });

  it("keeps people who have submitted nothing, so the roster stays complete", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([owner()]);

    render(<RosterSection token="tok" role="faculty" />);
    await userEvent.click(await screen.findByText("Ada Student"));

    expect(screen.getByText("Nothing waiting on you.")).toBeInTheDocument();
    expect(screen.getByText("No approved achievements yet.")).toBeInTheDocument();
  });

  it("filters the roster by name", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([
      owner(),
      owner({ owner_id: 8, name: "Grace Student", email: "grace@example.com" }),
    ]);

    render(<RosterSection token="tok" role="faculty" />);
    await screen.findByText("Ada Student");

    await userEvent.type(screen.getByLabelText("Search roster"), "grace");

    expect(screen.getByText("Grace Student")).toBeInTheDocument();
    expect(screen.queryByText("Ada Student")).not.toBeInTheDocument();
  });
});

describe("verifying from inside the roster", () => {
  it("offers the same decision controls the queue does and calls verify", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([
      owner({ pending: [record({ id: 42, title: "Pending Proof" })] }),
    ]);

    render(<RosterSection token="tok" role="faculty" />);
    await userEvent.click(await screen.findByText("Ada Student"));

    await userEvent.type(screen.getByLabelText("Remarks for Pending Proof"), "Looks genuine");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(achievementsApi.verify).toHaveBeenCalledWith("tok", 42, true, "Looks genuine");
  });

  it("declines through the same endpoint", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([
      owner({ pending: [record({ id: 42, title: "Pending Proof" })] }),
    ]);

    render(<RosterSection token="tok" role="faculty" />);
    await userEvent.click(await screen.findByText("Ada Student"));

    await userEvent.click(screen.getByRole("button", { name: "Decline" }));

    expect(achievementsApi.verify).toHaveBeenCalledWith("tok", 42, false, undefined);
  });

  it("reloads the roster after a decision so the record leaves the pending list", async () => {
    const byOwner = vi
      .spyOn(achievementsApi, "byOwner")
      .mockResolvedValueOnce([owner({ pending: [record({ id: 42, title: "Pending Proof" })] })])
      .mockResolvedValue([owner()]);

    render(<RosterSection token="tok" role="faculty" />);
    await userEvent.click(await screen.findByText("Ada Student"));
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(byOwner).toHaveBeenCalledTimes(2);
    expect(await screen.findByText("Nothing waiting on you.")).toBeInTheDocument();
  });

  it("surfaces a rejected decision instead of pretending it worked", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([
      owner({ pending: [record({ id: 42, title: "Pending Proof" })] }),
    ]);
    vi.spyOn(achievementsApi, "verify").mockRejectedValue(
      new Error("This record has already been reviewed.")
    );

    render(<RosterSection token="tok" role="faculty" />);
    await userEvent.click(await screen.findByText("Ada Student"));
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Could not update that record")).toBeInTheDocument();
  });
});

describe("HOD flow", () => {
  it("shows assigned faculty with the same expand-and-verify affordance", async () => {
    vi.spyOn(achievementsApi, "byOwner").mockResolvedValue([
      owner({
        owner_id: 3,
        owner_type: "employee",
        name: "Dr Turing",
        email: "turing@example.com",
        approved: [record({ id: 5, title: "Best Paper Award", status: "approved" })],
        pending: [record({ id: 6, title: "Conference Talk" })],
      }),
    ]);

    render(<RosterSection token="tok" role="hod" />);

    const heading = await screen.findByRole("heading", { name: "My Faculty" });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Faculty · turing@example.com/)).toBeInTheDocument();

    await userEvent.click(screen.getByText("Dr Turing"));

    expect(screen.getByText("Best Paper Award")).toBeInTheDocument();
    const pendingRow = screen.getByText("Conference Talk").closest(".roster-record") as HTMLElement;
    expect(within(pendingRow).getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });
});

describe("empty states", () => {
  it("tells a coordinator with no assigned students why the roster is empty", async () => {
    render(<RosterSection token="tok" role="faculty" />);

    expect(await screen.findByText("No students are assigned to you yet.")).toBeInTheDocument();
  });

  it("tells a HOD with no assigned faculty why the roster is empty", async () => {
    render(<RosterSection token="tok" role="hod" />);

    expect(await screen.findByText("No faculty are assigned to you yet.")).toBeInTheDocument();
  });
});
