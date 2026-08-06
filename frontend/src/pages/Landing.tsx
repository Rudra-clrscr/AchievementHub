import { useNavigate } from "react-router-dom";

const ROLE_CHOICES = [
  {
    key: "student",
    title: "Student",
    desc: "Submit your certificates, publications, and other achievements for verification.",
  },
  {
    key: "faculty",
    title: "Faculty & Admin",
    desc: "Review and verify achievement submissions from your students or department.",
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
                className="role-choice"
                onClick={() => navigate(`/login?as=${choice.key}`)}
              >
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
