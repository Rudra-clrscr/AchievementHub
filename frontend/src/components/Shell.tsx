import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";

export interface NavItem {
  key: string;
  label: string;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const chars = parts.length > 1 ? [parts[0][0], parts[parts.length - 1][0]] : [parts[0]?.[0] ?? "?"];
  return chars.join("").toUpperCase();
}

export function useDisplayName(token: string): string {
  const [name, setName] = useState("");
  useEffect(() => {
    let cancelled = false;
    api
      .me(token)
      .then((me) => {
        if (!cancelled) setName(me.name);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [token]);
  return name;
}

export function Sidebar({
  items,
  active,
  onSelect,
}: {
  items: NavItem[];
  active: string;
  onSelect: (key: string) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">AchievementHub</div>
      <nav className="sidebar-nav">
        {items.map((item) => (
          <button
            key={item.key}
            className={`sidebar-nav-item${active === item.key ? " active" : ""}`}
            onClick={() => onSelect(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-spacer" />
      <Link to="/" className="sidebar-nav-item sidebar-feed-link">
        ← Achievement Feed
      </Link>
    </aside>
  );
}

export function TopBar({ title, name, extra }: { title: string; name: string; extra?: React.ReactNode }) {
  const navigate = useNavigate();
  return (
    <header className="topbar">
      <div className="topbar-title">{title}</div>
      <div className="topbar-right">
        {extra}
        <input className="topbar-search" placeholder="Search achievements..." disabled />
        <button className="icon-btn" aria-label="Notifications" disabled>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
        </button>
        <button className="avatar" onClick={() => navigate("/profile")} title="View profile">
          {name ? initials(name) : "?"}
        </button>
      </div>
    </header>
  );
}
