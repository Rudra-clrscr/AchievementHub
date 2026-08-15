import { useNavigate } from "react-router-dom";

const CHOICES = [
  {
    key: "faculty",
    title: "Faculty",
    desc: "Submit your own achievements and review submissions from your assigned students.",
  },
  {
    key: "hod",
    title: "HOD",
    desc: "Review achievement submissions from the faculty assigned to you.",
  },
] as const;

export function AccessFacultyType() {
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
          <p className="auth-subtitle">Choose your role</p>

          <div className="role-choice-list">
            {CHOICES.map((choice) => (
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

          <p className="auth-footer">
            <a href="#" onClick={(e) => { e.preventDefault(); navigate("/access/role"); }}>
              &larr; Back
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
