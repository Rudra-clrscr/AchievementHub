import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  absoluteFileUrl,
  achievementsApi,
  type OwnerAchievementRecord,
  type OwnerAchievements,
} from "../api/client";
import { StatusBadge } from "./AchievementSection";

/** Whose roster this is, per role. Faculty coordinate students; a HOD
 * supervises faculty; an admin sits above both and gets the two mixed. */
export function rosterTitle(role: string): string {
  if (role === "hod") return "My Faculty";
  if (role === "admin") return "Department Roster";
  return "My Students";
}

function ownerInitial(name: string): string {
  return (name.trim()[0] ?? "?").toUpperCase();
}

function metaLine(record: OwnerAchievementRecord): string {
  const parts = [record.category];
  if (record.sub_category) parts.push(String(record.sub_category));
  return parts.join(" · ");
}

function remarksOf(record: OwnerAchievementRecord): string | null {
  const meta = record.metadata_fields;
  if (typeof meta === "object" && meta !== null && "remarks" in meta) {
    return String((meta as Record<string, unknown>).remarks);
  }
  return null;
}

function ProofLink({ record }: { record: OwnerAchievementRecord }) {
  return (
    <a className="queue-link" href={absoluteFileUrl(record.file_url)} target="_blank" rel="noreferrer">
      View file
    </a>
  );
}

/** A record still waiting on this verifier, with the same decision controls the
 * Verification Queue offers. Deliberately the identical `verify` call: the
 * roster is a second doorway onto the queue, not a second workflow. */
function PendingRow({
  record,
  onDecide,
}: {
  record: OwnerAchievementRecord;
  onDecide: (id: number, approve: boolean, remarks: string) => Promise<void>;
}) {
  const [remarks, setRemarks] = useState("");
  const [busy, setBusy] = useState<"approve" | "decline" | null>(null);

  const decide = async (approve: boolean) => {
    setBusy(approve ? "approve" : "decline");
    try {
      await onDecide(record.id, approve, remarks);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="roster-record roster-record-pending">
      <div className="roster-record-main">
        <div className="achievement-title">{record.title}</div>
        <div className="achievement-meta">
          {metaLine(record)} · submitted {new Date(record.submitted_at).toLocaleDateString()}
        </div>
      </div>
      <div className="roster-record-side">
        <ProofLink record={record} />
      </div>
      <div className="roster-decide">
        <input
          type="text"
          className="roster-remarks"
          placeholder="Add remarks (optional)..."
          aria-label={`Remarks for ${record.title}`}
          value={remarks}
          onChange={(e) => setRemarks(e.target.value)}
        />
        <div className="queue-actions">
          <button
            className="btn btn-outline btn-sm"
            disabled={busy !== null}
            onClick={() => decide(false)}
          >
            {busy === "decline" ? "Declining..." : "Decline"}
          </button>
          <button
            className="btn btn-approve btn-sm"
            disabled={busy !== null}
            onClick={() => decide(true)}
          >
            {busy === "approve" ? "Approving..." : "Approve"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ApprovedRow({ record }: { record: OwnerAchievementRecord }) {
  const remarks = remarksOf(record);
  return (
    <div className="roster-record">
      <div className="roster-record-main">
        <div className="achievement-title">{record.title}</div>
        <div className="achievement-meta">
          {metaLine(record)}
          {remarks ? ` · “${remarks}”` : ""}
        </div>
      </div>
      <div className="roster-record-side">
        <StatusBadge status={record.status} />
        <ProofLink record={record} />
        <span className="achievement-date">
          {record.approved_at ? new Date(String(record.approved_at)).toLocaleDateString() : ""}
        </span>
      </div>
    </div>
  );
}

function OwnerCard({
  owner,
  expanded,
  onToggle,
  onDecide,
}: {
  owner: OwnerAchievements;
  expanded: boolean;
  onToggle: () => void;
  onDecide: (id: number, approve: boolean, remarks: string) => Promise<void>;
}) {
  const kind = owner.owner_type === "employee" ? "Faculty" : "Student";
  return (
    <div className="roster-owner">
      <button
        type="button"
        className="roster-owner-head"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <span className={`achievement-avatar ${owner.owner_type === "employee" ? "avatar-publications" : "avatar-certificates"}`}>
          {ownerInitial(owner.name)}
        </span>
        <span className="roster-owner-identity">
          <span className="achievement-title">{owner.name}</span>
          <span className="achievement-meta">
            {kind} · {owner.email}
          </span>
        </span>
        <span className="roster-counts">
          <span className="badge badge-approved">{owner.approved.length} approved</span>
          {owner.pending.length > 0 && (
            <span className="badge badge-pending">{owner.pending.length} to verify</span>
          )}
        </span>
        <span className="roster-chevron" aria-hidden="true">
          {expanded ? "▾" : "▸"}
        </span>
      </button>

      {expanded && (
        <div className="roster-owner-body">
          <div className="roster-group-label">Awaiting your verification</div>
          {owner.pending.length === 0 ? (
            <div className="achievement-empty">Nothing waiting on you.</div>
          ) : (
            owner.pending.map((r) => <PendingRow key={r.id} record={r} onDecide={onDecide} />)
          )}

          <div className="roster-group-label">Approved achievements</div>
          {owner.approved.length === 0 ? (
            <div className="achievement-empty">No approved achievements yet.</div>
          ) : (
            owner.approved.map((r) => <ApprovedRow key={r.id} record={r} />)
          )}
        </div>
      )}
    </div>
  );
}

export function RosterSection({ token, role }: { token: string; role: string }) {
  const [owners, setOwners] = useState<OwnerAchievements[] | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const load = useCallback(() => {
    setError("");
    achievementsApi
      .byOwner(token)
      .then(setOwners)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load your roster");
        setOwners([]);
      });
  }, [token]);

  useEffect(load, [load]);

  // Decisions are made against the shared verify endpoint, so a reload is the
  // honest way to reflect the result: the record leaves this verifier's
  // actionable set, and (for an admin) lands in the approved list.
  const decide = async (id: number, approve: boolean, remarks: string) => {
    try {
      await achievementsApi.verify(token, id, approve, remarks || undefined);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update that record");
    }
  };

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return owners ?? [];
    return (owners ?? []).filter(
      (o) => o.name.toLowerCase().includes(term) || o.email.toLowerCase().includes(term)
    );
  }, [owners, search]);

  const totals = useMemo(() => {
    const all = owners ?? [];
    return {
      people: all.length,
      approved: all.reduce((n, o) => n + o.approved.length, 0),
      pending: all.reduce((n, o) => n + o.pending.length, 0),
    };
  }, [owners]);

  const keyOf = (o: OwnerAchievements) => `${o.owner_type}:${o.owner_id}`;

  const toggle = (o: OwnerAchievements) => {
    const key = keyOf(o);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const peopleLabel = role === "hod" ? "Faculty" : role === "admin" ? "People" : "Students";

  return (
    <>
      <div className="stat-grid">
        <div className="card stat-card">
          <div className="stat-card-label">{peopleLabel}</div>
          <div className="stat-card-value">{totals.people}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Approved Achievements</div>
          <div className="stat-card-value green">{totals.approved}</div>
        </div>
        <div className="card stat-card">
          <div className="stat-card-label">Awaiting You</div>
          <div className="stat-card-value orange">{totals.pending}</div>
        </div>
      </div>

      <div className="card section-card">
        <div className="section-header">
          <h2>{rosterTitle(role)}</h2>
          <input
            className="roster-search"
            type="search"
            placeholder="Search by name or email..."
            aria-label="Search roster"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {error && <p className="field-error">{error}</p>}
        {owners === null && <div className="achievement-empty">Loading…</div>}
        {owners !== null && owners.length === 0 && !error && (
          <div className="achievement-empty">
            {role === "hod"
              ? "No faculty are assigned to you yet."
              : role === "admin"
                ? "Nobody is registered in your department yet."
                : "No students are assigned to you yet."}
          </div>
        )}
        {owners !== null && owners.length > 0 && visible.length === 0 && (
          <div className="achievement-empty">Nobody matches “{search}”.</div>
        )}

        {visible.map((o) => (
          <OwnerCard
            key={keyOf(o)}
            owner={o}
            expanded={expanded.has(keyOf(o))}
            onToggle={() => toggle(o)}
            onDecide={decide}
          />
        ))}
      </div>
    </>
  );
}
