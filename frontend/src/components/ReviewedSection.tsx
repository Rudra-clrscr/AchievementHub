import { useCallback, useEffect, useState } from "react";
import {
  absoluteFileUrl,
  achievementsApi,
  type ReviewedAchievement,
  type ReviewedStatus,
} from "../api/client";
import { StatusBadge } from "./AchievementSection";

// Faculty and HODs sign off at tier 1 (pending -> verified); admins sign off at
// tier 2 (verified -> approved). Both land here, so the filter offers every
// state a reviewer can have left a record in. "verified" reads differently
// depending on who is looking, hence the role-aware label below.
const FILTERS: { key: ReviewedStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "verified", label: "Verified" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
];

function decisionDate(record: ReviewedAchievement, isAdmin: boolean): string {
  const stamp = isAdmin ? record.approved_at : record.verified_at;
  return stamp ? new Date(stamp).toLocaleDateString() : "";
}

export function ReviewedSection({ token, isAdmin }: { token: string; isAdmin: boolean }) {
  const [filter, setFilter] = useState<ReviewedStatus | "all">("all");
  const [records, setRecords] = useState<ReviewedAchievement[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setRecords(null);
    setError("");
    achievementsApi
      .reviewed(token, filter === "all" ? undefined : filter)
      .then(setRecords)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load your review history");
        setRecords([]);
      });
  }, [token, filter]);

  useEffect(load, [load]);

  return (
    <div className="card section-card">
      <div className="section-header">
        <h2>{isAdmin ? "Achievements You Approved" : "Achievements You Verified"}</h2>
      </div>

      <div className="form-actions" style={{ justifyContent: "flex-start", gap: 8 }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`btn btn-sm ${filter === f.key ? "btn-primary" : "btn-outline"}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && <p className="field-error">{error}</p>}
      {records === null && <div className="achievement-empty">Loading…</div>}
      {records !== null && records.length === 0 && !error && (
        <div className="achievement-empty">
          {filter === "all"
            ? "You have not reviewed anything yet."
            : `Nothing you reviewed is currently ${filter}.`}
        </div>
      )}

      {(records ?? []).map((r) => (
        <div className="achievement-row" key={r.id}>
          <div className="achievement-body">
            <div className="achievement-title">{r.title}</div>
            <div className="achievement-meta">
              {r.owner_name ?? "Unknown"} · {r.category}
              {r.sub_category ? ` · ${String(r.sub_category)}` : ""}
              {typeof r.metadata_fields === "object" &&
              r.metadata_fields !== null &&
              "remarks" in r.metadata_fields
                ? ` · “${String((r.metadata_fields as Record<string, unknown>).remarks)}”`
                : ""}
            </div>
          </div>
          <div className="achievement-right">
            <StatusBadge status={r.status} />
            <a
              className="queue-link"
              href={absoluteFileUrl(r.file_url)}
              target="_blank"
              rel="noreferrer"
            >
              View file
            </a>
            <span className="achievement-date">{decisionDate(r, isAdmin)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
