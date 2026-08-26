import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { feedApi, type FeedItem } from "../api/client";
import { PublicFeed } from "./PublicFeed";

/** The feed is the only page an unauthenticated visitor sees, so the things
 * worth pinning are that it renders approved work, that the filters are
 * visible and reversible, and that the decorative marquee stays out of the
 * accessibility tree. */

function item(over: Partial<FeedItem> = {}): FeedItem {
  return {
    id: 1,
    type: "certifications",
    title: "NPTEL Machine Learning",
    owner_type: "student",
    student_name: "Ada Student",
    category: "Certifications",
    verified_at: "2026-08-02T10:00:00Z",
    file_url: "https://cdn.example.com/proof.pdf",
    is_featured: false,
    ...over,
  };
}

function renderFeed() {
  return render(
    <MemoryRouter>
      <PublicFeed />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.spyOn(feedApi, "getTop").mockResolvedValue([]);
  vi.spyOn(feedApi, "getLatest").mockResolvedValue([]);
});

describe("the latest grid", () => {
  it("renders each approved achievement as a link to its detail page", async () => {
    vi.spyOn(feedApi, "getLatest").mockResolvedValue([item()]);

    renderFeed();

    const card = await screen.findByRole("link", { name: /NPTEL Machine Learning/ });
    expect(card).toHaveAttribute("href", "/achievement/certifications/1");
    expect(within(card).getByText("Ada Student")).toBeInTheDocument();
  });

  it("distinguishes a student's achievement from a faculty member's", async () => {
    vi.spyOn(feedApi, "getLatest").mockResolvedValue([
      item(),
      item({ id: 2, owner_type: "employee", student_name: "Dr Turing", title: "Best Paper" }),
    ]);

    renderFeed();

    // Scoped to the cards: "Faculty" is also an option in the Member select.
    const studentCard = await screen.findByRole("link", { name: /NPTEL Machine Learning/ });
    const facultyCard = screen.getByRole("link", { name: /Best Paper/ });
    expect(within(studentCard).getByText("Student")).toBeInTheDocument();
    expect(within(facultyCard).getByText("Faculty")).toBeInTheDocument();
  });

  it("falls back to a placeholder when a record has no thumbnail", async () => {
    vi.spyOn(feedApi, "getLatest").mockResolvedValue([item({ thumbnail_url: undefined })]);

    renderFeed();
    const card = await screen.findByRole("link", { name: /NPTEL Machine Learning/ });

    // No broken <img>; the card still carries its category.
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(within(card).getByText("Certifications")).toBeInTheDocument();
  });

  it("reports how many results the current filters produced", async () => {
    vi.spyOn(feedApi, "getLatest").mockResolvedValue([item(), item({ id: 2 })]);

    renderFeed();

    expect(await screen.findByText("2 results")).toBeInTheDocument();
  });
});

describe("filtering", () => {
  it("passes the search term, member and category to the backend", async () => {
    renderFeed();
    await screen.findByText("0 results");

    await userEvent.type(screen.getByLabelText("Search achievements by title"), "nptel");
    await userEvent.selectOptions(screen.getByLabelText("Member"), "student");

    await waitFor(() =>
      expect(feedApi.getLatest).toHaveBeenCalledWith({
        search: "nptel",
        category: "",
        owner_type: "student",
      })
    );
  });

  it("shows each active filter as a pill that removes just that filter", async () => {
    renderFeed();
    await screen.findByText("0 results");

    await userEvent.selectOptions(screen.getByLabelText("Member"), "student");
    await userEvent.selectOptions(screen.getByLabelText("Category"), "Certifications");

    const studentPill = await screen.findByRole("button", { name: /Students/ });
    expect(screen.getByRole("button", { name: /Certifications/ })).toBeInTheDocument();

    await userEvent.click(studentPill);

    expect(screen.queryByRole("button", { name: /Students/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Certifications/ })).toBeInTheDocument();
  });

  it("clears every filter at once", async () => {
    renderFeed();
    await screen.findByText("0 results");

    await userEvent.type(screen.getByLabelText("Search achievements by title"), "nptel");
    await userEvent.selectOptions(screen.getByLabelText("Member"), "student");

    await userEvent.click(await screen.findByRole("button", { name: "Clear all" }));

    await waitFor(() =>
      expect(feedApi.getLatest).toHaveBeenLastCalledWith({
        search: "",
        category: "",
        owner_type: "",
      })
    );
    expect(screen.queryByRole("button", { name: "Clear all" })).not.toBeInTheDocument();
  });

  it("drops a category the newly chosen member type cannot have", async () => {
    renderFeed();
    await screen.findByText("0 results");

    // "Certifications" is a student category; switching to Faculty must not
    // leave a filter selected that can never match.
    await userEvent.selectOptions(screen.getByLabelText("Category"), "Certifications");
    await userEvent.selectOptions(screen.getByLabelText("Member"), "employee");

    await waitFor(() =>
      expect(feedApi.getLatest).toHaveBeenLastCalledWith({
        search: "",
        category: "",
        owner_type: "employee",
      })
    );
  });

  it("offers a way out of an empty result set", async () => {
    renderFeed();
    await userEvent.type(await screen.findByLabelText("Search achievements by title"), "zzz");

    expect(await screen.findByText("No achievements match your filters")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    await waitFor(() =>
      expect(feedApi.getLatest).toHaveBeenLastCalledWith({
        search: "",
        category: "",
        owner_type: "",
      })
    );
  });
});

describe("spotlight", () => {
  it("is left out entirely when nothing is featured", async () => {
    renderFeed();
    await screen.findByText("0 results");

    expect(screen.queryByRole("heading", { name: "Spotlight" })).not.toBeInTheDocument();
  });

  it("links featured achievements and keeps the duplicated run out of the a11y tree", async () => {
    const featured = Array.from({ length: 4 }, (_, i) =>
      item({ id: i + 1, title: `Featured ${i + 1}`, is_featured: true })
    );
    vi.spyOn(feedApi, "getTop").mockResolvedValue(featured);

    renderFeed();

    expect(await screen.findByRole("heading", { name: "Spotlight" })).toBeInTheDocument();
    // The track renders twice so the marquee can wrap seamlessly, but only one
    // run is exposed -- otherwise every card would be announced twice.
    expect(screen.getAllByRole("link", { name: /Featured 1/ })).toHaveLength(1);
  });
});

describe("shell", () => {
  it("gives a visitor a way to sign in", async () => {
    renderFeed();

    const login = await screen.findByRole("link", { name: "Login to Submit" });
    expect(login).toHaveAttribute("href", "/landing");
  });
});
