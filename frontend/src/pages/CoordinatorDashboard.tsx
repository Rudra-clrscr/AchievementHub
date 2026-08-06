import { useState } from "react";
import { ACHIEVEMENT_TYPES } from "../achievementTypes";
import { useAuth } from "../auth/AuthContext";
import { AchievementPendingSection } from "../components/AchievementSection";
import { StudentAssignment } from "../components/StudentAssignment";
import { Sidebar, TopBar, useDisplayName, type NavItem } from "../components/Shell";

const ADMIN_ROLES = ["admin_hod", "admin_clerk"];
const STUDENTS_KEY = "students";

const ROLE_LABELS: Record<string, string> = {
  faculty_coordinator: "Faculty coordinator",
  admin_hod: "Admin (HOD)",
  admin_clerk: "Admin (Clerk)",
};

export function CoordinatorDashboard() {
  const { session } = useAuth();
  const isAdmin = ADMIN_ROLES.includes(session!.role);
  const navItems: NavItem[] = [
    ...ACHIEVEMENT_TYPES.map((t) => ({ key: t.key, label: t.label })),
    ...(isAdmin ? [{ key: STUDENTS_KEY, label: "Students" }] : []),
  ];
  const [view, setView] = useState<string>(ACHIEVEMENT_TYPES[0].key);
  const token = session!.token;
  const name = useDisplayName(token);
  const [pendingCount, setPendingCount] = useState(0);

  const activeType = ACHIEVEMENT_TYPES.find((t) => t.key === view);
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
              <div className="greeting-name">{activeType ? activeType.label : "Students"}</div>
            </div>
          </div>

          {activeType ? (
            <>
              <div className="stat-grid">
                <div className="card stat-card">
                  <div className="stat-card-label">Pending Review</div>
                  <div className="stat-card-value orange">{pendingCount}</div>
                </div>
              </div>

              <AchievementPendingSection
                key={activeType.key}
                title={activeType.label}
                idKey={activeType.idKey}
                fields={activeType.fields}
                api={activeType.api}
                token={token}
                category={activeType.key}
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
