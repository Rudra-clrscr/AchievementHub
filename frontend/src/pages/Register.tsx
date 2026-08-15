import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type Department } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ROLE_LABELS } from "../roles";

export function Register() {
  const [searchParams] = useSearchParams();
  const intent = searchParams.get("as") ?? "";
  const isEmployeeRole = intent === "faculty" || intent === "hod";

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [studentType, setStudentType] = useState<"inhouse" | "outhouse">("inhouse");
  const [departmentId, setDepartmentId] = useState("");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    api.departments().then(setDepartments).catch(() => setDepartments([]));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (isEmployeeRole) {
        await api.registerEmployee({
          name,
          email,
          password,
          role: intent as "faculty" | "hod",
          department_id: departmentId ? Number(departmentId) : undefined,
        });
        setSubmitted(true);
      } else {
        const { access_token, role } = await api.register({
          name,
          email,
          password,
          student_type: studentType,
          department_id: departmentId ? Number(departmentId) : undefined,
        });
        login(access_token, role);
        navigate("/student");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  };

  const roleLabel = ROLE_LABELS[intent] ?? intent;

  if (submitted) {
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
            <h1 className="auth-title">Registration submitted</h1>
            <p className="auth-subtitle">
              Your {roleLabel} account is pending admin approval. You'll be able to sign in once an admin reviews and approves it.
            </p>
            <p className="auth-footer">
              <Link to={`/login?as=${intent}`}>&larr; Back to sign in</Link>
            </p>
          </div>
        </div>
      </div>
    );
  }

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
          <h1 className="auth-title">{isEmployeeRole ? `Register as ${roleLabel}` : "Create an account"}</h1>
          <p className="auth-subtitle">
            {isEmployeeRole
              ? `Submit your details for admin approval. You'll be able to sign in once approved.`
              : "Register as a student to start submitting achievements"}
          </p>

          <form onSubmit={handleSubmit}>
            <div className="field">
              <label>Full name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="field">
              <label>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="field">
              <label>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
            {!isEmployeeRole && (
              <div className="field">
                <label>Student type</label>
                <select value={studentType} onChange={(e) => setStudentType(e.target.value as "inhouse" | "outhouse")}>
                  <option value="inhouse">Inhouse</option>
                  <option value="outhouse">Outhouse</option>
                </select>
              </div>
            )}
            {departments.length > 0 && (
              <div className="field">
                <label>Department</label>
                <select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
                  <option value="">Select department</option>
                  {departments.map((d) => (
                    <option key={d.dept_id} value={d.dept_id}>
                      {d.dept_name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {error && <p className="field-error">{error}</p>}
            <button className="btn btn-primary" type="submit" disabled={submitting} style={{ width: "100%" }}>
              {submitting ? "Submitting..." : isEmployeeRole ? "Submit for approval" : "Create account"}
            </button>
          </form>

          <p className="auth-footer">
            Already have an account? <Link to={intent ? `/login?as=${intent}` : "/login"}>Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
