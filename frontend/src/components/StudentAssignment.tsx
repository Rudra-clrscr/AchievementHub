import { useEffect, useState } from "react";
import { ApiError, studentsApi, type AdminStudent, type Coordinator } from "../api/client";

interface Props {
  token: string;
}

export function StudentAssignment({ token }: Props) {
  const [students, setStudents] = useState<AdminStudent[]>([]);
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

  const refresh = () => {
    studentsApi.list(token).then(setStudents).catch(() => setError("Failed to load students"));
    studentsApi.coordinators(token).then(setCoordinators).catch(() => setError("Failed to load coordinators"));
  };

  useEffect(refresh, [token]);

  const assign = async (studentId: number, coordinatorId: number) => {
    if (!coordinatorId) return;
    setError(null);
    setSavingId(studentId);
    try {
      const updated = await studentsApi.assignCoordinator(token, studentId, coordinatorId);
      setStudents((prev) => prev.map((s) => (s.student_id === studentId ? updated : s)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to assign coordinator");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="card section-card">
      <div className="section-header">
        <h2>Assign students to faculty coordinators</h2>
      </div>
      {error && <p className="field-error">{error}</p>}
      {coordinators.length === 0 && (
        <div className="achievement-empty">
          No faculty coordinators in your department yet — add one before assigning students.
        </div>
      )}
      {students.length === 0 && coordinators.length > 0 && (
        <div className="achievement-empty">No students to assign.</div>
      )}
      {students.map((s) => (
        <div className="queue-row" key={s.student_id}>
          <div className="achievement-avatar avatar-certificates">{s.name.charAt(0).toUpperCase()}</div>
          <div className="achievement-body">
            <div className="achievement-title">{s.name}</div>
            <div className="achievement-meta">
              {s.email}
              {" · "}
              {s.coordinator_name ? `Assigned to ${s.coordinator_name}` : "Unassigned"}
            </div>
          </div>
          <select
            className="assign-select"
            value={s.coordinator_id ?? ""}
            disabled={savingId === s.student_id || coordinators.length === 0}
            onChange={(e) => assign(s.student_id, Number(e.target.value))}
          >
            <option value="" disabled>
              Choose coordinator
            </option>
            {coordinators.map((c) => (
              <option key={c.emp_id} value={c.emp_id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
}
