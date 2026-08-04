import { useEffect, useMemo, useState } from "react";
import { ACHIEVEMENT_TYPES } from "../achievementTypes";
import type { AchievementRecord, UploadCategory } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AchievementSubmitSection } from "../components/AchievementSection";
import { Sidebar, TopBar, useDisplayName, type NavItem } from "../components/Shell";

const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", label: "Dashboard" },
  ...ACHIEVEMENT_TYPES.map((t) => ({ key: t.key, label: t.label })),
];

interface UnifiedRecord {
  key: string;
  typeKey: UploadCategory;
  typeLabel: string;
  title: string;
  record: AchievementRecord;
}

function DashboardOverview({ token, onAdd }: { token: string; onAdd: () => void }) {
  const name = useDisplayName(token);
  const [records, setRecords] = useState<UnifiedRecord[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      ACHIEVEMENT_TYPES.map((t) =>
        t.api.mine(token).then((rows) =>
          rows.map((r) => ({
            key: `${t.key}-${r[t.idKey]}`,
            typeKey: t.key,
            typeLabel: t.label,
            title: String(r[t.fields[0].name] ?? t.label),
            record: r,
          }))
        )
      )
    ).then((groups) => {
      if (cancelled) return;
      const merged = groups.flat().sort(
        (a, b) => new Date(b.record.submitted_at).getTime() - new Date(a.record.submitted_at).getTime()
      );
      setRecords(merged);
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const stats = useMemo(() => {
    const all = records ?? [];
    return {
      total: all.length,
      verified: all.filter((r) => r.record.status === "approved").length,
      pending: all.filter((r) => r.record.status === "pending").length,
      rejected: all.filter((r) => r.record.status === "rejected").length,
    };
  }, [records]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="greeting-eyebrow">Good to see you</div>
          <div className="greeting-name">{name || " "}</div>
        </div>
        <button className="btn btn-primary" onClick={onAdd}>
          + Add Achievement
        </button>
      </div>

      <div className="stat-grid">
        <div className="card stat-card">
          <div className="stat-card-label">Total Achievements</div>
          <div className="stat-card-value">{stats.total}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Verified</div>
          <div className="stat-card-value green">{stats.verified}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Pending Review</div>
          <div className="stat-card-value orange">{stats.pending}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Rejected</div>
          <div className="stat-card-value red">{stats.rejected}</div>
        </div>
      </div>

      <div className="card section-card">
        <div className="section-header">
          <h2>Recent Achievements</h2>
        </div>
        {records === null && <div className="achievement-empty">Loading...</div>}
        {records?.length === 0 && <div className="achievement-empty">Nothing submitted yet.</div>}
        {records?.slice(0, 8).map((r) => (
          <div className="achievement-row" key={r.key}>
            <div className={`achievement-avatar avatar-${r.typeKey}`}>{r.title.charAt(0).toUpperCase()}</div>
            <div className="achievement-body">
              <div className="achievement-title">{r.title}</div>
              <div className="achievement-meta">{r.typeLabel}</div>
            </div>
            <div className="achievement-right">
              <span className={`badge badge-${r.record.status === "approved" ? "approved" : r.record.status === "rejected" ? "rejected" : "pending"}`}>
                {r.record.status === "approved" ? "Verified" : r.record.status === "rejected" ? "Rejected" : "Pending Review"}
              </span>
              <span className="achievement-date">{new Date(r.record.submitted_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StudentDashboard() {
  const { session } = useAuth();
  const [view, setView] = useState("dashboard");
  const token = session!.token;
  const name = useDisplayName(token);

  const activeType = ACHIEVEMENT_TYPES.find((t) => t.key === view);

  return (
    <div className="app-shell">
      <Sidebar items={NAV_ITEMS} active={view} onSelect={setView} />
      <div className="main">
        <TopBar title={activeType ? activeType.label : "Dashboard"} name={name} />
        {view === "dashboard" ? (
          <DashboardOverview token={token} onAdd={() => setView("certificates")} />
        ) : activeType ? (
          <div className="page">
            <AchievementSubmitSection
              key={activeType.key}
              title={activeType.label}
              idKey={activeType.idKey}
              fields={activeType.fields}
              api={activeType.api}
              token={token}
              category={activeType.key}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
