import { useEffect, useState } from "react";
import { ApiError, employeesApi, type AdminFaculty, type Hod } from "../api/client";

interface Props {
  token: string;
}

export function FacultyAssignment({ token }: Props) {
  const [faculty, setFaculty] = useState<AdminFaculty[]>([]);
  const [hods, setHods] = useState<Hod[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

  const refresh = () => {
    employeesApi.listFaculty(token).then(setFaculty).catch(() => setError("Failed to load faculty"));
    employeesApi.listHods(token).then(setHods).catch(() => setError("Failed to load HODs"));
  };

  useEffect(refresh, [token]);

  const assign = async (empId: number, hodId: number) => {
    if (!hodId) return;
    setError(null);
    setSavingId(empId);
    try {
      const updated = await employeesApi.assignHod(token, empId, hodId);
      setFaculty((prev) => prev.map((f) => (f.emp_id === empId ? updated : f)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to assign HOD");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="card section-card">
      <div className="section-header">
        <h2>Assign faculty to HODs</h2>
      </div>
      {error && <p className="field-error">{error}</p>}
      {hods.length === 0 && (
        <div className="achievement-empty">No HODs in your department yet — add one before assigning faculty.</div>
      )}
      {faculty.length === 0 && hods.length > 0 && (
        <div className="achievement-empty">No faculty to assign.</div>
      )}
      {faculty.map((f) => (
        <div className="queue-row" key={f.emp_id}>
          <div className="achievement-avatar avatar-certificates">{f.name.charAt(0).toUpperCase()}</div>
          <div className="achievement-body">
            <div className="achievement-title">{f.name}</div>
            <div className="achievement-meta">
              {f.email}
              {" · "}
              {f.hod_name ? `Assigned to ${f.hod_name}` : "Unassigned"}
            </div>
          </div>
          <select
            className="assign-select"
            value={f.hod_id ?? ""}
            disabled={savingId === f.emp_id || hods.length === 0}
            onChange={(e) => assign(f.emp_id, Number(e.target.value))}
          >
            <option value="" disabled>
              Choose HOD
            </option>
            {hods.map((h) => (
              <option key={h.emp_id} value={h.emp_id}>
                {h.name}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}
