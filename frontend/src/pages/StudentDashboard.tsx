import { useEffect, useMemo, useState } from "react";
import { achievementsApi, STUDENT_CATEGORIES, type AchievementRecord } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AchievementSubmitSection, StatusBadge } from "../components/AchievementSection";
import { Sidebar, TopBar, useDisplayName, type NavItem } from "../components/Shell";

const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "submit", label: "Submit Achievement" },
];

function DashboardOverview({ token, onAdd }: { token: string; onAdd: () => void }) {
  const name = useDisplayName(token);
  const [records, setRecords] = useState<AchievementRecord[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    achievementsApi.mine(token).then((rows) => {
      if (!cancelled) setRecords(rows);
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const stats = useMemo(() => {
    const all = records ?? [];
    return {
      total: all.length,
<<<<<<< Updated upstream
      approved: all.filter((r) => r.status === "approved").length,
      verified: all.filter((r) => r.status === "verified").length,
      pending: all.filter((r) => r.status === "pending").length,
      rejected: all.filter((r) => r.status === "rejected").length,
=======
      verified: all.filter((r) => r.record.status === "approved").length,
      pending: all.filter((r) =>
        ["pending", "pending_hod", "pending_admin"].includes(r.record.status)
      ).length,
      rejected: all.filter((r) =>
        ["rejected", "revision_required"].includes(r.record.status)
      ).length,
>>>>>>> Stashed changes
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
          <div className="stat-card-label">Approved</div>
          <div className="stat-card-value green">{stats.approved}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Verified</div>
          <div className="stat-card-value gold">{stats.verified}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Pending Review</div>
          <div className="stat-card-value orange">{stats.pending}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Rejected / Revision</div>
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
          <div className="achievement-row" key={r.id as number}>
            <div className={`achievement-avatar avatar-${String(r.category).toLowerCase().replace(" ", "-")}`}>{String(r.title).charAt(0).toUpperCase()}</div>
            <div className="achievement-body">
              <div className="achievement-title">{String(r.title)}</div>
              <div className="achievement-meta">{String(r.category)}</div>
            </div>
            <div className="achievement-right">
<<<<<<< Updated upstream
              <StatusBadge status={r.status} />
              <span className="achievement-date">{new Date(r.submitted_at).toLocaleDateString()}</span>
=======
              <StatusBadge status={r.record.status} />
              <span className="achievement-date">{new Date(r.record.submitted_at).toLocaleDateString()}</span>
>>>>>>> Stashed changes
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

  return (
    <div className="app-shell">
      <Sidebar items={NAV_ITEMS} active={view} onSelect={setView} />
      <div className="main">
        <TopBar title={view === "dashboard" ? "Dashboard" : "Submit Achievement"} name={name} />
        {view === "dashboard" ? (
          <DashboardOverview token={token} onAdd={() => setView("submit")} />
        ) : (
          <div className="page">
            <AchievementSubmitSection
              title="Achievement"
              idKey="id"
              fields={[
                { name: "title", label: "Title", type: "text", required: true },
                { name: "category", label: "Category", type: "select", options: STUDENT_CATEGORIES, required: true },
                { name: "description", label: "Description", type: "textarea" },
                { name: "level", label: "Achievement Level", type: "select", options: ["", "College", "University", "State", "National", "International"] },
                { name: "date", label: "Date of Achievement", type: "date", required: true },
                { name: "organization", label: "Organization/Institution", type: "text" },
                { name: "event_name", label: "Event/Conference Name", type: "text" },
                { name: "team_or_individual", label: "Team or Individual", type: "select", options: ["", "Individual", "Team"] },
                { name: "start_date", label: "Start Date (if applicable)", type: "date" },
                { name: "end_date", label: "End Date (if applicable)", type: "date" },
                { name: "academic_year", label: "Academic Year (e.g. 2023-2024)", type: "text" },
                { name: "semester", label: "Semester", type: "select", options: ["", "1", "2", "3", "4", "5", "6", "7", "8"] },
              ]}
              api={achievementsApi}
              token={token}
              category="achievements"
            />
          </div>
        )}
      </div>
    </div>
  );
}
