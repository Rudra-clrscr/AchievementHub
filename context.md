# AchievementHub — Project Context

Working notes for contributors (and future AI sessions) on how this system is actually built, why certain decisions were made, and rules that exist because we already got burned. This is a technical companion to `README.md` (which is more of a feature pitch, and drifts from the real implementation in places — e.g. it still mentions AWS S3/Firebase and a 5MB compression threshold; neither is accurate).

**Update this file whenever the architecture actually changes** — it should describe what's true right now, not what was true when it was written. The "Team activity log" section at the bottom exists specifically to track schema/architecture-affecting work from other contributors, since coordination on this has been the project's biggest recurring problem so far (see below).

## Stack (actual)

- **Backend:** FastAPI (Python), SQLAlchemy ORM, Alembic migrations.
- **Database:** PostgreSQL, hosted on Supabase.
- **File storage:** Supabase Storage (not S3/Firebase) — only the public URL is ever persisted in Postgres, never raw file bytes.
- **Backend hosting:** Render, free tier — **0.1 vCPU**, limited RAM. This constraint drives a lot of the compression design (see below): bounded per-request latency and memory matter more than squeezing out the last few KB.
- **Frontend hosting:** Vercel. React + Vite + TypeScript.
- **Auth:** JWT (python-jose), password hashing via passlib.

## Data model (current, as of 2026-08-09)

Achievement data now lives in a **single unified `achievements` table** (`Achievement(AchievementMixin, Base)` in `backend/app/models.py`), with `category`/`sub_category` string columns and a `metadata_fields` JSON column for type-specific data (patent number, filing date, venue, etc). `backend/app/routers/achievements.py` is the one router handling submit/pending/verify for all types. The old per-type routers (`certificates.py`, `patents.py`, `publications.py`, `internships.py`, `events.py`) and their tables are gone.

This was **not** the original design and wasn't merged by agreement — see the incident log below. The original design used five separate typed tables (`Certificate`, `ResearchPublication`, `Patent`, `Internship`, `EventParticipation`) sharing common columns via `AchievementMixin`, for these reasons (still valid technical tradeoffs, worth knowing even though the unified table is what's live now):

1. Real, typed columns per type (`patent_number`, `filing_date`, `venue`, `start_date`/`end_date`, ...) instead of an untyped JSON blob where a missing/malformed field fails silently instead of at insert time.
2. Indexed queries stay fast — filtering/sorting on a real column is a normal index lookup; the same filter against a JSON blob is a slower, harder-to-index JSON-path query.
3. `AchievementMixin` + `build_achievement_router` already gave shared logic across five tables without a shared table — a unified table doesn't reduce code much further, it mainly trades away type safety.

The `Certificate` model/table has since been removed entirely (see incident log entry 2) — `models.py` now only defines `Achievement`, matching production.

### Incident log: unreviewed migrations against the shared production database

Two separate incidents, same root cause, worth reading before touching the schema:

1. **~2026-08-09, early:** A migration consolidating everything into a unified `achievements` table was run directly against the **shared production Supabase database** from a branch/commit that was never pushed to `main`. Result: `patents`, `research_publications`, `internships`, `event_participations` were dropped, a new empty `achievements` table appeared, and `alembic_version` was stamped at `ffc0eafda47c` — a revision that didn't exist in any migration file in the repo at the time. **All data in those four tables was lost** — no migration step copied it anywhere.
2. **~2026-08-09, later same day:** A second migration, again run directly against production before being committed anywhere (revision `6a30aab657aa`), dropped `certificates` and migrated its rows into `achievements`. This time the data *did* survive — all 13 rows verified intact (title, category, file_url, status, student_id all correct) — but the process was identical to incident 1: run against shared prod first, discovered after the fact rather than reviewed before. The migration file and the corresponding `Certificate` model removal were committed to `main` roughly an hour later ("chore: remove unused certificates table and model"), so this one is now at least fully reconciled in git — just not in the right order.
3. **~2026-08-09, same commit as incident 2:** That cleanup commit shipped with two bugs that took the *entire backend down* (reported as "authentication is broken" — it wasn't auth specifically, nothing worked): `schemas.py` still imported the now-deleted `CertificateCategory` enum, crashing the app at import time before any route could even register; and `Achievement.employee`/`Achievement.verifier` used `foreign_keys=[AchievementMixin.employee_id]`, which references the *mixin's* raw column descriptor rather than the concrete `Achievement` class's mapped column (declarative mixins clone their columns per subclass, so this never resolved to a real FK) — this threw `NoForeignKeysError` on any query touching the ORM relationship graph, e.g. `GET /departments`. Both fixed same day (commit "Fix backend startup crash and broken Achievement relationships"); verified with a full register → login → `/auth/me` → `/departments` → `/achievements/mine` flow run directly against the live production API, all `200`. Lesson: a change that only touches `models.py`/`schemas.py` still needs the app to actually be started and hit with a real request before merging — Python doesn't type-check itself, and SQLAlchemy relationship errors only surface at first-query time, not at import time.

Rules going forward, non-negotiable:
- **Never run `alembic upgrade`/`downgrade` against the shared production database from an unreviewed/unpushed branch.** Coordinate first, same as any other prod-affecting change. If a migration was worth running against prod, it was worth committing and pushing *before* running it.
- **Keep Alembic history linear.** Two migrations targeting the same parent revision (happened with `is_featured`, added independently on two branches) creates divergent heads that `alembic upgrade head` can't resolve without a merge migration. Check `alembic heads` shows exactly one head before merging a PR that touches `alembic/versions/`.
- Experiment with schema changes against a local/throwaway Postgres instance, not the Supabase project `backend/.env` points at.

## Upload compression (`backend/app/uploads.py`)

Every uploaded file (any type, any size — that's a selling point of the app) is either compressed or stored as-is, then pushed to Supabase Storage; only the URL is persisted. Compression exists because raw files would otherwise bloat both storage and the 0.1 vCPU host's per-request time. Design principles, most non-obvious first:

- **Whole-file target is 250KB** (`TARGET_MAX_FILE_SIZE`), with a 60KB **per-image floor** (`MIN_PER_IMAGE_BUDGET`) that actually governs multi-image documents — for anything with 5+ embedded images, the floor dominates the per-image budget math regardless of what the whole-file target is set to, so multi-image PDFs/OOXML aren't meaningfully affected by tightening the whole-file number. The floor exists specifically so a 20+ page scanned PDF doesn't get crushed to mush chasing an unrealistic total; legibility wins over hitting the target exactly.
- **Speed over ratio, deliberately.** The host has 0.1 vCPU. Every knob (WebP `method=1` instead of higher search effort, JPEG for photos instead of WebP, no `optimize=True` on JPEG saves, JPEG draft-mode decoding instead of full-res-then-shrink) was chosen after measuring the actual speed/size tradeoff on this host, not assumed.
- **Content-aware routing.** `_classify_image` buckets each image as `photo` (continuous tone → JPEG, fastest and JPEG's natural domain), `graphic` (flat-color UI/diagrams → WebP, since JPEG rings visibly on flat color/sharp edges), or `text` (near-bilevel scans → WebP/PNG lossless first, since lossy quantization blurs small text). This routing is the reason JPEG isn't used everywhere despite being faster — it would visibly hurt quality on the two other content types.
- **Never store something bigger than what was uploaded.** Every compression path (image, PDF, OOXML) is checked against the original size before being kept; if compression didn't help, the original bytes are used instead. This also applies **per-image** inside PDF/OOXML recompression, not just at the whole-file level — a single image inflating can otherwise hide inside a net-smaller file.
- **PDF recompression has two non-obvious failure modes that were found and fixed the hard way:**
  - `page.replace_image()` (PyMuPDF) always creates a throwaway replacement object internally; if you don't call `page.clean_contents(sanitize=True)` afterward, that throwaway object survives garbage collection as an orphaned-but-referenced duplicate, silently doubling every recompressed image's storage cost. Was live in production before being caught.
  - `doc.subset_fonts()` looks like a great, cheap size win in isolation (60%+ off font-heavy synthetic tests) but **silently corrupts Type0/CID-keyed fonts** on real-world files (Illustrator-exported PDF text rendered as disconnected marks, no exception thrown to catch it). Do not re-add font subsetting without rendering and eyeballing real output first — a successful `tobytes()` call proves nothing about whether the text is still readable.
- **Editor round-trip metadata is dead weight.** PDFs from design tools (seen from Adobe Illustrator) can embed the *entire native source file* via `PieceInfo`/`AIPDFPrivateData*`, purely so the tool can reopen it for further editing — no PDF viewer ever reads it. Stripping it is lossless for anyone just viewing the file and can be the single biggest size win on such files (measured: one real file went from 2.43MB to 159KB, zero image/font changes).
- **Bounded, not perfect.** A wall-clock budget (`RECOMPRESS_TIME_BUDGET_SECONDS`) caps total per-file recompression time regardless of page/image count. Some large multi-image documents (e.g. a 51-page slide deck with 9+ real images) legitimately won't hit the 250KB target without visible quality loss — the target is a goal, not a guarantee.

## Review history: the two verification signatures (`achievements.verified_by` vs `approved_by`)

A verifier can see everything they have personally signed off, at
`GET /achievements/reviewed` and under **Review History** in the coordinator
dashboard. Faculty and HODs see what they verified; admins see what they
approved. Optional `?status=verified|approved|rejected` filters the list.

**This needed a schema change to work at all.** Both tiers used to write
`verified_by`/`verified_at`, so an admin approval overwrote the coordinator who
did tier 1. A coordinator asking "what have I reviewed?" would have lost
precisely the records that completed the pipeline — the ones they would most
want to see. Migration `e5c71b9a3d80` adds `approved_by`/`approved_at`; tier 2
now signs those and leaves `verified_by` alone.

Things worth knowing before touching this:

- **History is keyed off the signature, not off the scope filters.** Scope
  answers "what may I review *now*?" and legitimately changes — a student is
  reassigned to another coordinator, a faculty member moves department. History
  must not rewrite itself when that happens. If you signed it, you can still
  see it.
- **One record can appear for two people, and that is correct.** The
  coordinator who verified it and the admin who then approved it each reviewed
  it, and each sees it in their own list.
- **A multi-role employee gets a different list per active role**, matching how
  the rest of the app treats the role picked at login: what they verified as
  faculty and what they approved as admin are separate histories.
- **The list is ordered and dated by the acting tier's own timestamp** —
  `approved_at` for an admin, `verified_at` for everyone else. Using
  `submitted_at` for both would make the two lists indistinguishable.
- **Migrations are applied by hand, always.** `render.yaml` runs
  `pip install` then `uvicorn` -- nothing calls `alembic upgrade`, so a deploy
  never migrates. `e5c71b9a3d80` was applied to production on 2026-08-25 via
  the Supabase SQL editor (rendered with `alembic upgrade <from>:<to> --sql`,
  run inside a single transaction, with `alembic_version` stamped in the same
  transaction). Any future migration needs the same treatment; merging a PR
  does not migrate anything.
- **Backfill limits.** The migration copies `verified_by` into `approved_by`
  for rows already `approved`, since for those the last actor was an admin. The
  original tier-1 verifier on those rows is genuinely unrecoverable — it was
  overwritten before the column existed — so it is left as-is rather than
  invented. Rows in `rejected` are left alone entirely: either tier can reject
  and the data cannot say which one did. **Pre-migration history is therefore
  approximate; everything from this migration forward is exact.**

## Tests (`backend/tests/`)

Run them from `backend/`:

```
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

220 tests, ~20 seconds, no setup and no services. What to know before adding to them:

- **They cannot reach production.** `tests/conftest.py` pins `DATABASE_URL` to in-memory SQLite *before* `app.*` is imported (env vars outrank `backend/.env` in pydantic-settings), then asserts that the URL the app actually resolved is the test one and refuses to start otherwise. Never weaken that assertion — the suite calls `drop_all()` between every test.
- **SQLite is the default, not the whole story.** Set `TEST_DATABASE_URL` to a scratch Postgres database to run the same suite against the real dialect. Worth doing before trusting a migration: SQLite will not reproduce Postgres-specific behaviour such as the missing `json` equality operator that forced `union_all()` instead of `union()` in the pending queue.
- **bcrypt runs at 4 rounds in tests** (`pwd_context.update(bcrypt__default_rounds=4)`). This is what takes the suite from two minutes to five seconds; production cost is untouched. A suite nobody waits for is a suite nobody runs.
- **`tests/conftest.py` holds a `Factory`** that builds departments, sections, employees with role sets, students, and achievements. Use it rather than hand-rolling objects, and use the `as_employee` / `as_student` / `as_pending_employee` fixtures for auth headers — `as_employee(person, role)` mints a token for one *active* role, which is how a multi-role account actually behaves per session.

What is covered, and why those things:

| File | Protects |
|---|---|
| `test_auth.py` | Who can get a token for what role: pre-login role choice, the role picker, unapproved employees, self-registration limits, section-derived department/year, and that a pending role-selection token opens nothing role-gated |
| `test_achievements.py` | The `pending -> verified -> approved` pipeline, plus every scope filter: faculty see their own students, HODs see their assigned faculty, admins see their department, principals see nothing |
| `test_employees_admin.py` | The 2026-08-18 one-HOD regression from both sides, HOD assignment, registration approval, and admin-only gating on every endpoint |
| `test_students_admin.py` | The Department-Year-Section hierarchy, including the section-coordinator cascade onto already-enrolled students |
| `test_feed.py` | The only unauthenticated read surface — that nothing unapproved reaches it through any filter |
| `test_uploads.py` | The compression pipeline: content classification, the never-grow and never-corrupt invariants, OOXML media keeping its original format, and the fallback to raw bytes when compression fails. `httpx.post` is replaced by a recorder, so it also pins exactly what would be sent to Supabase Storage |

**The regression tests are load-bearing, not decorative.** Re-introducing the pre-fix `assign_hod` guard makes three tests in `test_employees_admin.py` fail in five seconds with the exact production symptom (`403 "A different HOD is already assigned to this department"`). That check was verified by actually doing it, not assumed.

Two bugs the suite found on its first run, both now fixed:

- **Verifier remarks were silently discarded on any record that already had metadata.** `verify_achievement` mutated `record.metadata_fields` in place and reassigned the same dict object. `metadata_fields` is a plain `JSON` column with no mutation tracking, so SQLAlchemy saw no net change (`History(added=(), unchanged=[...])`), dropped the column from the `UPDATE`, and the remarks vanished. Records with `NULL` metadata worked *by accident*, because `or {}` produced a genuinely new object — which is exactly why it survived manual testing: the plain-certificate case is the one anyone would try by hand. Patents, publications and internships carry metadata, so rejecting one told the student nothing about why. Fixed by building a new dict. **If you ever add another writer to a JSON column, do the same or wrap the column in `MutableDict`.**
- No CI existed. See below.

### Frontend tests (`frontend/src/**/*.test.{ts,tsx}`)

Run them from `frontend/`:

```
npm install
npm test
```

41 tests on vitest + jsdom + Testing Library. `vitest.config.ts` is deliberately
separate from `vite.config.ts` so nothing about the test setup can reach the
production build. `src/test/setup.ts` pins `VITE_API_BASE` so URL assertions do
not depend on a developer's `.env`, and clears storage between tests.

The weight is on `src/api/client.ts`, because that is where the non-obvious
behaviour lives:

- **Cold-start retries.** Network-level failures are retried on a
  `[1s, 3s, 8s, 15s]` backoff; genuine HTTP errors are not, since retrying a 401
  cannot change the answer and would turn every failed login into five requests.
  Both halves of that rule are pinned.
- **`uploadFile` must not set `Content-Type`.** Setting it by hand omits the
  multipart boundary and the backend rejects every upload. There is a test
  asserting the header is absent.

Note that `tsc -b` type-checks the test files too (they live under `src`), so a
broken mock signature fails `npm run build`. That is intentional -- CI runs the
build after the tests for exactly that reason.

## CI (`.github/workflows/tests.yml`)

Three jobs on every push to `main` and every PR:

- **`pytest`** — the suite above. No secrets, no service containers.
- **`frontend`** — vitest, then `npm run build` (which type-checks).
- **`migrations`** — asserts Alembic has exactly one head. A branch whose migration sets `down_revision` to an older revision forks the graph, and `alembic upgrade head` then fails outright against production. That has already happened on this repo and is still sitting unmerged on `origin/dev-main`; this catches it at PR time instead of at deploy time.

This repo takes merges from several people plus two bot authors (`google-labs-jules`, `copilot-swe-agent`). CI is what makes those PRs reviewable rather than hand-tested.

## Free-tier hosting quirks worth knowing

- Render's free-tier backend spins down when idle and cold-starts on the next request. While booting, requests fail at the network level (no HTTP response at all), which browsers report as a **CORS block** even though CORS itself is configured correctly — there's just no response to carry the headers. The frontend retries network-level failures with backoff (`frontend/src/api/client.ts`) to ride this out transparently; don't chase a reported "CORS error" at face value without first checking whether it's actually this.

## Team activity log

Running log of schema/architecture-affecting work landing from other contributors, kept because coordination has been the project's weak point. Add an entry whenever a PR or direct prod change touches the schema, the achievement data model, or upload/storage behavior.

- **2026-08-09 — Rachit (`rachit_branch`, PRs #2 and #3 + follow-up commits):** Added thumbnail generation/storage, `is_featured`, redesigned the public feed to a YouTube-style thumbnail grid with a detail page, and — the major change — consolidated all achievement types (including certificates) into the single `achievements` table described above. Landed via two direct-to-production migrations that were initially never committed to any branch (see incident log above); both are now reconciled in git after the fact. PR #3 removed the five per-type routers and the old `achievementTypes.ts` frontend file; a later commit removed the now-dead `Certificate` model and added the matching migration, but shipped with the two bugs in incident log entry 3 that took the whole backend down for a stretch until fixed the same day. `frontend/src/api/client.ts` gained `achievementsApi` (replacing the five separate `*Api` objects) and student/faculty category lists (`STUDENT_CATEGORIES`/`FACULTY_CATEGORIES`) driving the unified submit form. As of this writing, the unified-table approach is fully live in both code and production DB — the project owner's initial "revert to separate tables" request in team chat has not been acted on either way; worth a direct conversation rather than assuming either outcome.
