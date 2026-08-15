import { useEffect, useState } from "react";
import { ApiError, employeesApi, type PendingEmployee } from "../api/client";
import { ROLE_LABELS } from "../roles";

interface Props {
  token: string;
}

export function PendingRegistrations({ token }: Props) {
  const [pending, setPending] = useState<PendingEmployee[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<number | null>(null);

  const refresh = () => {
    employeesApi.listPending(token).then(setPending).catch(() => setError("Failed to load pending registrations"));
  };

  useEffect(refresh, [token]);

  const approve = async (empId: number) => {
    setError(null);
    setActingId(empId);
    try {
      await employeesApi.approve(token, empId);
      setPending((prev) => prev.filter((p) => p.emp_id !== empId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to approve registration");
    } finally {
      setActingId(null);
    }
  };

  const reject = async (empId: number) => {
    setError(null);
    setActingId(empId);
    try {
      await employeesApi.reject(token, empId);
      setPending((prev) => prev.filter((p) => p.emp_id !== empId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to reject registration");
    } finally {
      setActingId(null);
    }
  };

  return (
    <div className="card section-card">
      <div className="section-header">
        <h2>Pending registrations</h2>
      </div>
      {error && <p className="field-error">{error}</p>}
      {pending.length === 0 && <div className="achievement-empty">No pending registrations.</div>}
      {pending.map((p) => (
        <div className="queue-row" key={p.emp_id}>
          <div className="achievement-avatar avatar-certificates">{p.name.charAt(0).toUpperCase()}</div>
          <div className="achievement-body">
            <div className="achievement-title">
              {p.name} — {ROLE_LABELS[p.requested_role] ?? p.requested_role}
            </div>
            <div className="achievement-meta">
              {p.email}
              {" · "}
              {p.department_name ?? "No department"}
            </div>
          </div>
          <div className="queue-actions">
            <button className="btn btn-outline btn-sm" disabled={actingId === p.emp_id} onClick={() => reject(p.emp_id)}>
              Reject
            </button>
            <button className="btn btn-approve btn-sm" disabled={actingId === p.emp_id} onClick={() => approve(p.emp_id)}>
              Approve
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
