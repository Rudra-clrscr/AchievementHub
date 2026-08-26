import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { feedApi, type FeedItem, absoluteFileUrl, STUDENT_CATEGORIES, FACULTY_CATEGORIES } from "../api/client";
import "./PublicFeed.css";

/** The feed's `type` is a slug of the achievement's category, so there is no
 * fixed set to hand-colour -- categories are free-form strings that grow with
 * the product. Hash the category into a small curated palette instead: the
 * same category always gets the same accent, and a new one still arrives
 * looking deliberate rather than defaulting to a flat grey tile. */
const ACCENTS = 8;

function accentOf(value: string | null | undefined): number {
  const text = (value ?? "").trim().toLowerCase();
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = (hash * 31 + text.charCodeAt(i)) % 100003;
  }
  return hash % ACCENTS;
}

function initialOf(name: string | null): string {
  return (name?.trim()[0] ?? "F").toUpperCase();
}

function formatDate(dateString: string | null): string {
  if (!dateString) return "";
  return new Date(dateString).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" strokeLinecap="round" />
    </svg>
  );
}

function FeedCard({ item }: { item: FeedItem }) {
  const accent = accentOf(item.category);
  const isStudent = item.owner_type === "student";

  return (
    <Link to={`/achievement/${item.type}/${item.id}`} className={`feed-card accent-${accent}`}>
      <div className="feed-thumb">
        {item.thumbnail_url ? (
          <img src={absoluteFileUrl(item.thumbnail_url)} alt="" loading="lazy" />
        ) : (
          <div className="feed-thumb-fallback" aria-hidden="true">
            <span className="feed-thumb-initial">{initialOf(item.title)}</span>
          </div>
        )}
        {item.is_featured && <span className="feed-flag">Featured</span>}
        {item.category && <span className="feed-chip">{item.category}</span>}
      </div>

      <div className="feed-card-body">
        <span className="feed-avatar" aria-hidden="true">
          {initialOf(item.student_name)}
        </span>
        <span className="feed-card-text">
          <span className="feed-card-title" title={item.title}>
            {item.title}
          </span>
          <span className="feed-card-author">
            {item.student_name || "Faculty Member"}
            <span className={`feed-role ${isStudent ? "is-student" : "is-faculty"}`}>
              {isStudent ? "Student" : "Faculty"}
            </span>
          </span>
          {item.verified_at && (
            <span className="feed-card-date">Verified {formatDate(item.verified_at)}</span>
          )}
        </span>
      </div>
    </Link>
  );
}

/** Placeholder cards sized like real ones. Swapping a text "Loading..." for
 * these keeps the grid from collapsing and reflowing on every keystroke of the
 * debounced search. */
function SkeletonGrid() {
  return (
    <div className="feed-grid" aria-hidden="true">
      {Array.from({ length: 8 }, (_, i) => (
        <div className="feed-card feed-card-skeleton" key={i}>
          <div className="feed-thumb skeleton-block" />
          <div className="feed-card-body">
            <span className="feed-avatar skeleton-block" />
            <span className="feed-card-text">
              <span className="skeleton-line" />
              <span className="skeleton-line short" />
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function PublicFeed() {
  const [topItems, setTopItems] = useState<FeedItem[]>([]);
  const [latestItems, setLatestItems] = useState<FeedItem[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [ownerType, setOwnerType] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    feedApi.getTop().then(setTopItems).catch(console.error);
  }, []);

  useEffect(() => {
    setLoading(true);
    const delay = setTimeout(() => {
      feedApi
        .getLatest({ search, category, owner_type: ownerType })
        .then(setLatestItems)
        .catch(console.error)
        .finally(() => setLoading(false));
    }, 300); // debounce search
    return () => clearTimeout(delay);
  }, [search, category, ownerType]);

  const ownerLabel = ownerType === "student" ? "Students" : ownerType === "employee" ? "Faculty" : "";
  const activeFilters = useMemo(
    () =>
      [
        search.trim() && { key: "search", label: `“${search.trim()}”`, clear: () => setSearch("") },
        ownerLabel && { key: "owner", label: ownerLabel, clear: () => setOwnerType("") },
        category && { key: "category", label: category, clear: () => setCategory("") },
      ].filter(Boolean) as { key: string; label: string; clear: () => void }[],
    [search, ownerLabel, category]
  );

  const clearAll = () => {
    setSearch("");
    setCategory("");
    setOwnerType("");
  };

  // Marquee scrolls by translating exactly half its content, so the duplicate
  // run is what makes the loop seamless. With only a couple of cards there is
  // nothing to scroll past and the loop reads as a stutter, so the animation
  // is left to the stylesheet to switch off below that threshold.
  const marqueeRuns = topItems.length >= 4 ? [false, true] : [false];

  return (
    <div className="feed-page">
      <header className="feed-topbar">
        <div className="feed-topbar-inner">
          <Link to="/" className="feed-brand">
            <span className="feed-brand-mark" aria-hidden="true">
              &#10003;
            </span>
            AchievementHub
          </Link>
          <Link to="/landing" className="feed-btn">
            Login to Submit
          </Link>
        </div>
      </header>

      <div className="feed-shell">
        <section className="feed-hero">
          <p className="feed-eyebrow">Public showcase</p>
          <h1 className="feed-hero-title">Achievements from across the campus</h1>
          <p className="feed-hero-sub">
            Every certificate, publication, patent and award below has been verified and approved
            by the institution.
          </p>
        </section>

        {topItems.length > 0 && (
          <section className="feed-spotlight">
            <div className="feed-section-head">
              <h2 className="feed-section-title">Spotlight</h2>
              {marqueeRuns.length > 1 && <span className="feed-section-note">Hover to pause</span>}
            </div>

            <div className={`feed-marquee${marqueeRuns.length > 1 ? "" : " is-static"}`}>
              <div className={`feed-marquee-track${marqueeRuns.length > 1 ? " is-scrolling" : ""}`}>
                {marqueeRuns.map((isClone) =>
                  topItems.map((item) => (
                    <Link
                      to={`/achievement/${item.type}/${item.id}`}
                      key={`${isClone ? "clone" : "run"}-${item.type}-${item.id}`}
                      className={`spotlight-card accent-${accentOf(item.category)}`}
                      // The duplicated run exists only so the loop can wrap; it
                      // is the same content twice, so keep it out of the
                      // accessibility tree and out of the tab order.
                      aria-hidden={isClone || undefined}
                      tabIndex={isClone ? -1 : undefined}
                    >
                      <span className="spotlight-chip">{item.category}</span>
                      <span className="spotlight-title">{item.title}</span>
                      <span className="spotlight-author">
                        {item.student_name || "Faculty Member"}
                      </span>
                    </Link>
                  ))
                )}
              </div>
            </div>
          </section>
        )}

        <section className="feed-controls" aria-label="Filter achievements">
          <div className="feed-search">
            <span className="feed-search-icon">
              <SearchIcon />
            </span>
            <input
              id="feed-search-input"
              type="search"
              placeholder="Search achievements by title..."
              aria-label="Search achievements by title"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="feed-selects">
            <label className="feed-select">
              <span className="feed-select-label">Member</span>
              <select
                value={ownerType}
                onChange={(e) => {
                  const newOwner = e.target.value;
                  setOwnerType(newOwner);
                  if (newOwner === "student" && !STUDENT_CATEGORIES.includes(category)) {
                    setCategory("");
                  } else if (newOwner === "employee" && !FACULTY_CATEGORIES.includes(category)) {
                    setCategory("");
                  }
                }}
              >
                <option value="">All members</option>
                <option value="student">Students</option>
                <option value="employee">Faculty</option>
              </select>
            </label>

            <label className="feed-select">
              <span className="feed-select-label">Category</span>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {(!ownerType || ownerType === "student") && (
                  <optgroup label="Student categories">
                    {STUDENT_CATEGORIES.map((c) => (
                      <option key={`student-${c}`} value={c}>
                        {c}
                      </option>
                    ))}
                  </optgroup>
                )}
                {(!ownerType || ownerType === "employee") && (
                  <optgroup label="Faculty categories">
                    {FACULTY_CATEGORIES.map((c) => (
                      <option key={`faculty-${c}`} value={c}>
                        {c}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </label>
          </div>
        </section>

        {activeFilters.length > 0 && (
          <div className="feed-active-filters">
            {activeFilters.map((f) => (
              <button key={f.key} type="button" className="feed-filter-pill" onClick={f.clear}>
                {f.label}
                <span aria-hidden="true">×</span>
                <span className="sr-only">Remove filter</span>
              </button>
            ))}
            <button type="button" className="feed-clear-all" onClick={clearAll}>
              Clear all
            </button>
          </div>
        )}

        <section className="feed-results">
          <div className="feed-section-head">
            <h2 className="feed-section-title">Latest achievements</h2>
            <span className="feed-count" aria-live="polite">
              {loading
                ? "Loading…"
                : `${latestItems.length} ${latestItems.length === 1 ? "result" : "results"}`}
            </span>
          </div>

          {loading ? (
            <SkeletonGrid />
          ) : latestItems.length === 0 ? (
            <div className="feed-empty">
              <p className="feed-empty-title">No achievements match your filters</p>
              <p className="feed-empty-sub">Try a different search term or widen the category.</p>
              {activeFilters.length > 0 && (
                <button type="button" className="feed-btn feed-btn-outline" onClick={clearAll}>
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <div className="feed-grid">
              {latestItems.map((item) => (
                <FeedCard item={item} key={`${item.type}-${item.id}`} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
