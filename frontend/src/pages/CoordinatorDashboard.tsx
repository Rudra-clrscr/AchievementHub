import { useState } from "react";
import { achievementsApi } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AchievementPendingSection } from "../components/AchievementSection";
import { StudentAssignment } from "../components/StudentAssignment";
import { Sidebar, TopBar, useDisplayName, type NavItem } from "../components/Shell";

const ADMIN_ROLES = ["admin_hod", "admin_clerk"];

const ROLE_LABELS: Record<string, string> = {
  faculty_coordinator: "Faculty coordinator",
  admin_hod: "Admin (HOD)",
  admin_clerk: "Admin (Clerk)",
};

export function CoordinatorDashboard() {
  const { session } = useAuth();
  const isAdmin = ADMIN_ROLES.includes(session!.role);
  const navItems: NavItem[] = [
    { key: "achievements", label: "Achievements" },
    ...(isAdmin ? [{ key: "students", label: "Students" }] : []),
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
        <TopBar title="Verification Queue" name={name} />
        <div className="page">
          <div className="page-header">
            <div>
              <div className="greeting-eyebrow">{roleLabel}</div>
              <div className="greeting-name">{view === "achievements" ? "Pending Achievements" : "Students"}</div>
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
          ) : (
            <StudentAssignment token={token} />
          )}
        </div>
      </div>
    </div>
  );
}
