import { useEffect, useState } from "react";
import {
  ApiError,
  absoluteFileUrl,
  uploadFile,
  type AchievementRecord,
  type UploadCategory,
} from "../api/client";

export interface FieldConfig {
  name: string;
  label: string;
  type: "text" | "date" | "select";
  options?: string[];
  required?: boolean;
}

export interface AchievementApi {
  submit: (token: string, payload: Record<string, unknown>) => Promise<AchievementRecord>;
  mine: (token: string) => Promise<AchievementRecord[]>;
  pending: (token: string) => Promise<AchievementRecord[]>;
  verify: (token: string, id: number, approve: boolean) => Promise<AchievementRecord>;
}

interface StudentProps {
  title: string;
  idKey: string;
  fields: FieldConfig[];
  api: AchievementApi;
  token: string;
  category: UploadCategory;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === "approved" ? "badge-approved" : status === "rejected" ? "badge-rejected" : "badge-pending";
  const label = status === "approved" ? "Verified" : status === "rejected" ? "Rejected" : "Pending Review";
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function AchievementSubmitSection({ title, idKey, fields, api, token, category }: StudentProps) {
  const emptyForm = Object.fromEntries(fields.map((f) => [f.name, f.type === "select" ? f.options?.[0] ?? "" : ""]));
  const [form, setForm] = useState<Record<string, string>>(emptyForm);
  const [file, setFile] = useState<File | null>(null);
  const [records, setRecords] = useState<AchievementRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<"uploading" | "saving" | null>(null);
  const [lastCompression, setLastCompression] = useState<string | null>(null);
  const submitting = stage !== null;

  const refresh = () => {
    api.mine(token).then(setRecords).catch(() => setError(`Failed to load ${title.toLowerCase()}`));
  };

  useEffect(refresh, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!file) {
      setError("Attach a file (any type, any size) to submit.");
      return;
    }
    setStage("uploading");
    try {
      const uploaded = await uploadFile(token, category, file);
      setLastCompression(
        `Uploaded ${formatBytes(uploaded.original_size)} -> stored ${formatBytes(uploaded.stored_size)}`
      );

      const payload: Record<string, unknown> = { file_url: uploaded.file_url };
      for (const f of fields) {
        if (form[f.name]) payload[f.name] = form[f.name];
      }
      setStage("saving");
      await api.submit(token, payload);
      setForm(emptyForm);
      setFile(null);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submission failed");
    } finally {
      setStage(null);
    }
  };

  const STAGE_LABEL: Record<string, string> = {
    uploading: "Compressing & uploading...",
    saving: "Saving...",
  };

  const titleField = fields[0];
  const metaFields = fields.slice(1);

  return (
    <>
      <form className="card section-card" onSubmit={handleSubmit}>
        <h2>Add {title.toLowerCase()}</h2>
        <p className="greeting-eyebrow" style={{ marginBottom: 18 }}>
          Fill in the details and attach your proof — any file type or size, we compress it automatically.
        </p>

        <div className="form-section-label">Details</div>
        <div className="form-grid">
          {fields.map((f) => (
            <div className={`field${f.type === "select" ? "" : ""}`} key={f.name}>
              <label>{f.label}</label>
              {f.type === "select" ? (
                <select value={form[f.name]} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}>
                  {f.options?.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={f.type}
                  value={form[f.name]}
                  onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
                  required={f.required}
                />
              )}
            </div>
          ))}
        </div>

        <div className="form-section-label">Proof & Documents</div>
        <label className="file-drop">
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          {file ? (
            <span className="file-drop-name">{file.name}</span>
          ) : (
            <>
              <span className="file-drop-title">Click to choose your proof file</span>
              <span className="file-drop-hint">Any file type, any size — compressed automatically</span>
            </>
          )}
        </label>
        {lastCompression && <p className="compression-note">{lastCompression}</p>}
        {error && <p className="field-error">{error}</p>}

        <div className="form-actions">
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting && <span className="btn-spinner" aria-hidden="true" />}
            {stage ? STAGE_LABEL[stage] : "Submit for verification"}
          </button>
        </div>
      </form>

      <div className="card section-card">
        <div className="section-header">
          <h2>Your submissions</h2>
        </div>
        {records.length === 0 && <div className="achievement-empty">Nothing submitted yet.</div>}
        {records.map((r) => (
          <div className="achievement-row" key={String(r[idKey])}>
            <div className={`achievement-avatar avatar-${category}`}>
              {String(r[titleField.name] ?? "?").charAt(0).toUpperCase()}
            </div>
            <div className="achievement-body">
              <div className="achievement-title">{String(r[titleField.name] ?? "")}</div>
              <div className="achievement-meta">
                {metaFields
                  .map((f) => r[f.name])
                  .filter(Boolean)
                  .join(" · ") || title}
              </div>
            </div>
            <div className="achievement-right">
              <StatusBadge status={r.status} />
              <span className="achievement-date">{new Date(r.submitted_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

interface CoordinatorProps {
  title: string;
  idKey: string;
  fields: FieldConfig[];
  api: AchievementApi;
  token: string;
  category: UploadCategory;
  onCountChange?: (count: number) => void;
}

export function AchievementPendingSection({ title, idKey, fields, api, token, category, onCountChange }: CoordinatorProps) {
  const [records, setRecords] = useState<AchievementRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    api
      .pending(token)
      .then((rows) => {
        setRecords(rows);
        onCountChange?.(rows.length);
      })
      .catch(() => setError(`Failed to load pending ${title.toLowerCase()}`));
  };

  useEffect(refresh, [token]);

  const decide = async (id: number, approve: boolean) => {
    setError(null);
    try {
      await api.verify(token, id, approve);
      refresh();
    } catch {
      setError("Failed to update record");
    }
  };

  const titleField = fields[0];
  const metaFields = fields.slice(1);

  return (
    <div className="card section-card">
      <div className="section-header">
        <h2>Pending {title.toLowerCase()}</h2>
      </div>
      {error && <p className="field-error">{error}</p>}
      {records.length === 0 && <div className="achievement-empty">Nothing pending.</div>}
      {records.map((r) => (
        <div className="queue-row" key={String(r[idKey])}>
          <div className={`achievement-avatar avatar-${category}`}>
            {String(r[titleField.name] ?? "?").charAt(0).toUpperCase()}
          </div>
          <div className="achievement-body">
            <div className="achievement-title">
              Student #{String(r.student_id ?? "")} — {String(r[titleField.name] ?? "")}
            </div>
            <div className="achievement-meta">
              {metaFields
                .map((f) => r[f.name])
                .filter(Boolean)
                .join(" · ")}
              {" · "}
              {new Date(r.submitted_at).toLocaleDateString()}
            </div>
          </div>
          <a className="queue-link" href={absoluteFileUrl(r.file_url)} target="_blank" rel="noreferrer">
            View
          </a>
          <div className="queue-actions">
            <button className="btn btn-outline btn-sm" onClick={() => decide(Number(r[idKey]), false)}>
              Decline
            </button>
            <button className="btn btn-approve btn-sm" onClick={() => decide(Number(r[idKey]), true)}>
              Approve
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
