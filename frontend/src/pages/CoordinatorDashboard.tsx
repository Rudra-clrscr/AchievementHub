import { useState } from "react";
import { ACHIEVEMENT_TYPES } from "../achievementTypes";
import { useAuth } from "../auth/AuthContext";
import { AchievementPendingSection } from "../components/AchievementSection";
import { Sidebar, TopBar, useDisplayName, type NavItem } from "../components/Shell";

const NAV_ITEMS: NavItem[] = ACHIEVEMENT_TYPES.map((t) => ({ key: t.key, label: t.label }));

export function CoordinatorDashboard() {
  const { session } = useAuth();
  const [view, setView] = useState<string>(ACHIEVEMENT_TYPES[0].key);
  const token = session!.token;
  const name = useDisplayName(token);
  const [pendingCount, setPendingCount] = useState(0);

  const activeType = ACHIEVEMENT_TYPES.find((t) => t.key === view)!;

  return (
    <div className="app-shell">
      <Sidebar items={NAV_ITEMS} active={view} onSelect={setView} />
      <div className="main">
        <TopBar title="Verification Queue" name={name} />
        <div className="page">
          <div className="page-header">
            <div>
              <div className="greeting-eyebrow">Faculty coordinator</div>
              <div className="greeting-name">{activeType.label}</div>
            </div>
          </div>

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
        </div>
      </div>
    </div>
  );
}
