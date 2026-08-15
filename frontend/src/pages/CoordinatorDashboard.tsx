import { useEffect, useMemo, useState } from "react";
import { achievementsApi, FACULTY_CATEGORIES, type AchievementRecord } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AchievementPendingSection, AchievementSubmitSection, StatusBadge } from "../components/AchievementSection";
import { StudentAssignment } from "../components/StudentAssignment";
import { FacultyAssignment } from "../components/FacultyAssignment";
import { PendingRegistrations } from "../components/PendingRegistrations";
import { Sidebar, TopBar, useDisplayName, type NavItem } from "../components/Shell";
import { ROLE_LABELS } from "../roles";

const ADMIN_ROLES = ["admin"];

function DashboardOverview({ token, onAdd }: { token: string; onAdd: () => void }) {
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
      approved: all.filter((r) => r.status === "approved").length,
      verified: all.filter((r) => r.status === "verified").length,
      pending: all.filter((r) => r.status === "pending").length,
      rejected: all.filter((r) => r.status === "rejected").length,
    };
  }, [records]);

  return (
    <>
      <div className="page-header">
        <div>
          <div className="greeting-eyebrow">Your Achievements</div>
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
          <div className="stat-card-label">Rejected</div>
          <div className="stat-card-value red">{stats.rejected}</div>
        </div>
      </div>

      <div className="card section-card">
        <div className="section-header">
          <h2>Recent Submissions</h2>
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
              <StatusBadge status={r.status} />
              <span className="achievement-date">{new Date(r.submitted_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}


export function CoordinatorDashboard() {
  const { session } = useAuth();
  const isAdmin = ADMIN_ROLES.includes(session!.role);
  const navItems: NavItem[] = [
    { key: "achievements", label: "Verification Queue" },
    { key: "my_achievements", label: "My Achievements" },
    { key: "submit", label: "Submit Achievement" },
    ...(isAdmin
      ? [
          { key: "students", label: "Students" },
          { key: "faculty", label: "Faculty" },
          { key: "registrations", label: "Registrations" },
        ]
      : []),
  ];
  const [view, setView] = useState<string>("achievements");
  const token = session!.token;
  const name = useDisplayName(token);
  const [pendingCount, setPendingCount] = useState(0);

  const roleLabel = ROLE_LABELS[session!.role] ?? session!.role;

  return (
    <div className="app-shell">
      <Sidebar items={navItems} active={view} onSelect={setView} />
      <div className="main">
        <TopBar
          title={
            view === "achievements"
              ? "Verification Queue"
              : view === "submit"
                ? "Submit Achievement"
                : view === "students"
                  ? "Student Roster"
                  : view === "faculty"
                    ? "Faculty Roster"
                    : view === "registrations"
                      ? "Pending Registrations"
                      : "My Achievements"
          }
          name={name}
        />
        <div className="page">
          <div className="page-header">
            <div>
              <div className="greeting-eyebrow">{roleLabel}</div>
              <div className="greeting-name">{name || " "}</div>
            </div>
          </div>

          {view === "achievements" ? (
            <>
              <div className="stat-grid">
                <div className="card stat-card">
                  <div className="stat-card-label">Pending Review</div>
                  <div className="stat-card-value orange">{pendingCount}</div>
                </div>
              </div>

              <AchievementPendingSection
                key="achievements"
                title="Achievements"
                idKey="id"
                fields={[
                  { name: "title", label: "Title", type: "text" },
                  { name: "category", label: "Category", type: "text" },
                ]}
                api={achievementsApi}
                token={token}
                category="achievements"
                onCountChange={setPendingCount}
              />
            </>
          ) : view === "my_achievements" ? (
            <DashboardOverview token={token} onAdd={() => setView("submit")} />
          ) : view === "submit" ? (
            <div className="page">
            <AchievementSubmitSection
              title="Faculty Achievement"
              idKey="id"
              fields={[
                { name: "title", label: "Title", type: "text", required: true },
                { name: "category", label: "Category", type: "select", options: FACULTY_CATEGORIES, required: true },
                { name: "description", label: "Description", type: "textarea" },
                { name: "level", label: "Achievement Level", type: "select", options: ["", "College", "University", "State", "National", "International"] },
                { name: "date", label: "Date of Achievement", type: "date", required: true },
                { name: "organization", label: "Organization/Institution", type: "text" },
                { name: "event_name", label: "Event/Conference Name", type: "text" },
              ]}
              api={achievementsApi}
              token={token}
              category="achievements"
            />
          </div>
          ) : view === "students" ? (
            <StudentAssignment token={token} />
          ) : view === "faculty" ? (
            <FacultyAssignment token={token} />
          ) : (
            <PendingRegistrations token={token} />
          )}
        </div>
      </div>
    </div>
  );
}
