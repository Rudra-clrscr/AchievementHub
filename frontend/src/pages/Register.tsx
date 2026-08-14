import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type Department } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function Register() {
  const [searchParams] = useSearchParams();
  const intent = searchParams.get("as") ?? "";
  const isInstitutionalRole = intent === "faculty" || intent === "hod";

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [studentType, setStudentType] = useState<"inhouse" | "outhouse">("inhouse");
  const [departmentId, setDepartmentId] = useState("");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isInstitutionalRole) {
      api.departments().then(setDepartments).catch(() => setDepartments([]));
    }
  }, [isInstitutionalRole]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { access_token, role } = await api.register({
        name,
        email,
        password,
        student_type: studentType,
        department_id: departmentId ? Number(departmentId) : undefined,
      });
      login(access_token, role);
      navigate("/student");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  };

  const roleLabel = intent === "hod" ? "HOD" : "Faculty";

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
          <h1 className="auth-title">
            {isInstitutionalRole ? `${roleLabel} Access` : "Create an account"}
          </h1>
          <p className="auth-subtitle">
            {isInstitutionalRole
              ? `${roleLabel} accounts are provisioned by the institution. Please sign in with your institutional credentials.`
              : "Register as a student to start submitting achievements"}
          </p>

          {isInstitutionalRole ? (
            <div style={{ marginTop: "1.5rem", textAlign: "center" }}>
              <Link to={`/login?as=${intent}`} className="btn btn-primary" style={{ display: "block", textDecoration: "none" }}>
                Sign in as {roleLabel}
              </Link>
            </div>
          ) : (
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
              <div className="field">
                <label>Student type</label>
                <select value={studentType} onChange={(e) => setStudentType(e.target.value as "inhouse" | "outhouse")}>
                  <option value="inhouse">Inhouse</option>
                  <option value="outhouse">Outhouse</option>
                </select>
              </div>
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
                {submitting ? "Creating account..." : "Create account"}
              </button>
            </form>
          )}

          <p className="auth-footer">
            Already have an account? <Link to={intent ? `/login?as=${intent}` : "/login"}>Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
