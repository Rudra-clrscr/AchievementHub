import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, achievementsApi, type AchievementRecord, type MeResponse } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import "./Profile.css";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const chars = parts.length > 1 ? [parts[0][0], parts[parts.length - 1][0]] : [parts[0]?.[0] ?? "?"];
  return chars.join("").toUpperCase();
}

export function Profile() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  const token = session?.token ?? "";

  const [me, setMe] = useState<MeResponse | null>(null);
  const [achievements, setAchievements] = useState<AchievementRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.me(token), achievementsApi.mine(token)])
      .then(([meResult, mine]) => {
        setMe(meResult);
        setAchievements(mine);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [token]);

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const record of achievements) {
      const category = (record.category as string | undefined) || "Uncategorized";
      counts.set(category, (counts.get(category) ?? 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [achievements]);

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  if (loading) {
    return <div className="profile-loading">Loading profile...</div>;
  }

  return (
    <div className="profile-page">
      <div className="profile-card">
        <button className="profile-back" onClick={() => navigate(-1)} aria-label="Go back">
          ← Back
        </button>

        <div className="profile-header">
          <div className="profile-avatar">{me ? initials(me.name) : "?"}</div>
          <div>
            <h1 className="profile-name">{me?.name ?? "Unknown"}</h1>
            <div className="profile-email">{me?.email}</div>
          </div>
        </div>

        <div className="profile-section">
          <h2 className="profile-section-title">Achievements by category</h2>
          {categoryCounts.length === 0 ? (
            <p className="profile-empty">No achievements submitted yet.</p>
          ) : (
            <ul className="profile-category-list">
              {categoryCounts.map(([category, count]) => (
                <li key={category} className="profile-category-row">
                  <span className="profile-category-name">{category}</span>
                  <span className="profile-category-count">{count}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="profile-total">
            Total: <strong>{achievements.length}</strong>
          </div>
        </div>

        <button className="profile-logout" onClick={handleLogout}>
          Log out
        </button>
      </div>
    </div>
  );
}
