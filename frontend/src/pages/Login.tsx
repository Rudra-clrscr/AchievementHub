import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ROLE_LABELS } from "../roles";

const SUBTITLE_BY_INTENT: Record<string, string> = {
  student: "Sign in to submit and track your achievements",
  faculty: "Sign in to review and verify student submissions",
  hod: "Sign in to review submissions from your assigned faculty",
  admin: "Sign in to manage assignments and publish verified achievements",
};

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [roleChoices, setRoleChoices] = useState<string[] | null>(null);
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const intent = searchParams.get("as") ?? "";
  const subtitle = SUBTITLE_BY_INTENT[intent] ?? "Sign in to continue to your AchievementHub account";

  const enterSession = (accessToken: string, role: string) => {
    login(accessToken, role);
    navigate(role === "student" ? "/student" : "/coordinator");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await api.login(email, password, intent || undefined);
      if (result.requires_role_selection) {
        setRoleChoices(result.roles ?? []);
        setPendingToken(result.pending_token ?? null);
      } else {
        enterSession(result.access_token!, result.role!);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSelectRole = async (role: string) => {
    if (!pendingToken) return;
    setError(null);
    setSubmitting(true);
    try {
      const result = await api.selectRole(pendingToken, role);
      enterSession(result.access_token!, result.role!);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not continue with that role");
    } finally {
      setSubmitting(false);
    }
  };

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
          {roleChoices ? (
            <>
              <h1 className="auth-title">Continue as...</h1>
              <p className="auth-subtitle">This account holds more than one role. Choose which one to sign in as.</p>

              {error && <p className="field-error">{error}</p>}

              <div className="form-actions" style={{ flexDirection: "column", gap: "0.6rem" }}>
                {roleChoices.map((role) => (
                  <button
                    key={role}
                    className="btn btn-primary"
                    type="button"
                    disabled={submitting}
                    style={{ width: "100%" }}
                    onClick={() => handleSelectRole(role)}
                  >
                    {ROLE_LABELS[role] ?? role}
                  </button>
                ))}
              </div>

              <p className="auth-footer">
                <a href="#" onClick={(e) => { e.preventDefault(); setRoleChoices(null); setPendingToken(null); }}>
                  &larr; Back to sign in
                </a>
              </p>
            </>
          ) : (
            <>
              <h1 className="auth-title">Welcome back</h1>
              <p className="auth-subtitle">{subtitle}</p>

              <form onSubmit={handleSubmit}>
                <div className="field">
                  <label>Email</label>
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
                </div>
                <div className="field">
                  <label>Password</label>
                  <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </div>
                {error && <p className="field-error">{error}</p>}
                <button className="btn btn-primary" type="submit" disabled={submitting} style={{ width: "100%" }}>
                  {submitting ? "Signing in..." : "Sign in"}
                </button>
              </form>

              {intent !== "admin" && (
                <p className="auth-footer">
                  New to AchievementHub?{" "}
                  <Link to={intent ? `/register?as=${intent}` : "/register"}>Create an account</Link>
                </p>
              )}
              <p className="auth-footer">
                <Link to="/">&larr; Back</Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
