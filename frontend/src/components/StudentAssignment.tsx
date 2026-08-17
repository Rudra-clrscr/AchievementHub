import { useEffect, useState } from "react";
import { api, ApiError, studentsApi, type AdminStudent, type Coordinator, type Department, type Section } from "../api/client";

interface Props {
  token: string;
}

export function StudentAssignment({ token }: Props) {
  const [students, setStudents] = useState<AdminStudent[]>([]);
  const [coordinators, setCoordinators] = useState<Coordinator[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);

  // Section batch assignment state
  const [selectedYear, setSelectedYear] = useState<string>("3");
  const [sections, setSections] = useState<Section[]>([]);
  const [selectedSectionId, setSelectedSectionId] = useState<string>("");
  const [batchCoordinatorId, setBatchCoordinatorId] = useState<string>("");
  const [batchSaving, setBatchSaving] = useState<boolean>(false);
  const [batchSuccess, setBatchSuccess] = useState<string | null>(null);

  const refresh = () => {
    studentsApi.list(token).then(setStudents).catch(() => setError("Failed to load students"));
    studentsApi.coordinators(token).then(setCoordinators).catch(() => setError("Failed to load coordinators"));
  };

  useEffect(refresh, [token]);

  const [selectedDeptId, setSelectedDeptId] = useState<string>("");
  const [departments, setDepartments] = useState<Department[]>([]);

  useEffect(() => {
    api.departments().then((depts) => {
      setDepartments(depts);
      if (depts.length > 0) setSelectedDeptId(String(depts[0].dept_id));
    }).catch(() => setDepartments([]));
  }, []);

  // Load sections when selectedYear or selectedDeptId changes
  useEffect(() => {
    if (selectedYear && selectedDeptId) {
      api.sections(Number(selectedDeptId), Number(selectedYear))
        .then(setSections)
        .catch(() => setSections([]));
    } else {
      setSections([]);
    }
  }, [selectedYear, selectedDeptId]);

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

  const assignBatchSection = async () => {
    if (!selectedSectionId || !batchCoordinatorId) return;
    setError(null);
    setBatchSuccess(null);
    setBatchSaving(true);
    try {
      await studentsApi.assignSectionCoordinator(token, Number(selectedSectionId), Number(batchCoordinatorId));
      setBatchSuccess("Batch coordinator assigned to section successfully!");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed batch section assignment");
    } finally {
      setBatchSaving(false);
    }
  };

  return (
    <div className="card section-card">
      <div className="section-header">
        <h2>Assign students to faculty coordinators</h2>
      </div>

      {/* Batch Section Coordinator Assignment Control */}
      <div style={{ background: "rgba(255,255,255,0.03)", padding: "16px", borderRadius: "8px", marginBottom: "24px", border: "1px solid rgba(255,255,255,0.08)" }}>
        <h3 style={{ fontSize: "14px", fontWeight: "600", marginBottom: "12px" }}>⚡ Batch Assign Coordinator by Section</h3>
        <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
          <select className="assign-select" value={selectedDeptId} onChange={(e) => { setSelectedDeptId(e.target.value); setSelectedSectionId(""); }}>
            {departments.map((d) => (
              <option key={d.dept_id} value={d.dept_id}>
                {d.dept_name}
              </option>
            ))}
          </select>

          <select className="assign-select" value={selectedYear} onChange={(e) => { setSelectedYear(e.target.value); setSelectedSectionId(""); }}>
            <option value="1">1st Year</option>
            <option value="2">2nd Year</option>
            <option value="3">3rd Year</option>
            <option value="4">4th Year</option>
          </select>

          <select className="assign-select" value={selectedSectionId} onChange={(e) => setSelectedSectionId(e.target.value)}>
            <option value="">Select Section</option>
            {sections.map((sec) => (
              <option key={sec.section_id} value={sec.section_id}>
                {sec.section_name}
              </option>
            ))}
          </select>

          <select className="assign-select" value={batchCoordinatorId} onChange={(e) => setBatchCoordinatorId(e.target.value)}>
            <option value="">Select Faculty Coordinator</option>
            {coordinators.map((c) => (
              <option key={c.emp_id} value={c.emp_id}>
                {c.name}
              </option>
            ))}
          </select>

          <button className="btn btn-primary" onClick={assignBatchSection} disabled={batchSaving || !selectedSectionId || !batchCoordinatorId}>
            {batchSaving ? "Assigning..." : "Assign to Section Batch"}
          </button>
        </div>
        {batchSuccess && <p style={{ color: "#4caf50", fontSize: "13px", marginTop: "8px" }}>{batchSuccess}</p>}
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
              {s.year ? ` · Year ${s.year}` : ""}
              {s.section_name ? ` · Sec ${s.section_name}` : ""}
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
