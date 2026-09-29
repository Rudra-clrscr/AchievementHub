import { useNavigate } from "react-router-dom";

const ROLE_CHOICES = [
  {
    key: "student",
    title: "Student",
    desc: "Submit your certificates, publications, and other achievements for verification.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 10v6M2 10l10-5 10 5-10 5z"/>
        <path d="M6 12v5c3 3 9 3 12 0v-5"/>
      </svg>
    )
  },
  {
    key: "faculty",
    title: "Faculty & Admin",
    desc: "Review and verify achievement submissions from your students or department.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
        <circle cx="9" cy="7" r="4"/>
        <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
    )
  },
] as const;

export function Landing() {
  const navigate = useNavigate();

  return (
    <div className="auth-shell">
      <div className="auth-panel-dark">
        <div className="auth-logo">
          <span className="auth-logo-mark">&#10003;</span>
          AchievementHub
        </div>
        <div className="auth-tagline">Digital repository for academic excellence</div>
      </div>

      <div className="auth-panel-form">
        <div className="auth-card">
          <h1 className="auth-title">Continue as</h1>
          <p className="auth-subtitle">Choose how you'd like to access AchievementHub</p>

          <div className="role-choice-list">
            {ROLE_CHOICES.map((choice) => (
              <button
                key={choice.key}
                type="button"
                className={`role-choice role-choice-${choice.key}`}
                onClick={() => navigate(choice.key === "faculty" ? "/access/role" : `/login?as=${choice.key}`)}
              >
                <div className="role-choice-icon">{choice.icon}</div>
                <span className="role-choice-title">{choice.title}</span>
                <span className="role-choice-desc">{choice.desc}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
