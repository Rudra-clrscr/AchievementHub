import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { feedApi, type FeedItem, absoluteFileUrl } from "../api/client";
import "./PublicFeed.css";

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

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "N/A";
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <div className="public-feed-container">
      {/* Top Section - Horizontal Marquee */}
      <section className="top-achievements-section">
        <h2 className="section-title">Top Achievements 🏆</h2>
        <div className="marquee-container">
          <div className="marquee-content">
            {topItems.map((item) => (
              <div key={`top-${item.type}-${item.id}`} className="marquee-card">
                <span className="marquee-badge">{item.category}</span>
                <h4>{item.title}</h4>
                <p className="marquee-author">By {item.student_name || "Faculty Member"}</p>
              </div>
            ))}
            {/* Duplicate for seamless scrolling */}
            {topItems.map((item) => (
              <div key={`top-dup-${item.type}-${item.id}`} className="marquee-card">
                <span className="marquee-badge">{item.category}</span>
                <h4>{item.title}</h4>
                <p className="marquee-author">By {item.student_name || "Faculty Member"}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Middle Section - Search & Filters */}
      <section className="search-filter-section glass-panel">
        <div className="search-bar">
          <input
            type="text"
            placeholder="Search achievements by title..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="filters">
          <select value={ownerType} onChange={(e) => setOwnerType(e.target.value)}>
            <option value="">All Members</option>
            <option value="student">Students</option>
            <option value="employee">Faculty</option>
          </select>

          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All Categories</option>
            <optgroup label="Academic & Research">
              <option value="publication">Publications</option>
              <option value="patent">Patents</option>
              <option value="certificate">Certificates</option>
            </optgroup>
            <optgroup label="Professional & Extracurricular">
              <option value="internship">Internships</option>
              <option value="event">Events & Hackathons</option>
              <option value="sports">Sports</option>
            </optgroup>
          </select>
        </div>
        <div className="login-link">
          <Link to="/landing" className="btn-primary">Login to Submit</Link>
        </div>
      </section>

      {/* Bottom Section - Latest Vertical Feed */}
      <section className="latest-achievements-section">
        <h3 className="section-title">Latest Achievements ✨</h3>
        {loading ? (
          <div className="loading-spinner">Loading feed...</div>
        ) : (
          <div className="feed-grid">
            {latestItems.length === 0 ? (
              <div className="no-results">No achievements found matching your criteria.</div>
            ) : (
              latestItems.map((item) => (
                <div key={`${item.type}-${item.id}`} className="feed-card glass-panel">
                  <div className="feed-card-header">
                    <span className={`category-tag ${item.type}`}>{item.category}</span>
                    <span className="date-tag">{formatDate(item.verified_at)}</span>
                  </div>
                  <h3 className="feed-title">{item.title}</h3>
                  <div className="feed-author">
                    <strong>{item.owner_type === "student" ? "Student" : "Faculty"}:</strong>{" "}
                    {item.student_name || "N/A"}
                  </div>
                  <div className="feed-actions">
                    <a
                      href={absoluteFileUrl(item.file_url)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-secondary"
                    >
                      View Document
                    </a>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </section>
    </div>
  );
}
