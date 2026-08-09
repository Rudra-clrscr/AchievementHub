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

## Free-tier hosting quirks worth knowing

- Render's free-tier backend spins down when idle and cold-starts on the next request. While booting, requests fail at the network level (no HTTP response at all), which browsers report as a **CORS block** even though CORS itself is configured correctly — there's just no response to carry the headers. The frontend retries network-level failures with backoff (`frontend/src/api/client.ts`) to ride this out transparently; don't chase a reported "CORS error" at face value without first checking whether it's actually this.

## Team activity log

Running log of schema/architecture-affecting work landing from other contributors, kept because coordination has been the project's weak point. Add an entry whenever a PR or direct prod change touches the schema, the achievement data model, or upload/storage behavior.

- **2026-08-09 — Rachit (`rachit_branch`, PRs #2 and #3 + follow-up commits):** Added thumbnail generation/storage, `is_featured`, redesigned the public feed to a YouTube-style thumbnail grid with a detail page, and — the major change — consolidated all achievement types (including certificates) into the single `achievements` table described above. Landed via two direct-to-production migrations that were initially never committed to any branch (see incident log above); both are now reconciled in git after the fact. PR #3 removed the five per-type routers and the old `achievementTypes.ts` frontend file; a later commit removed the now-dead `Certificate` model and added the matching migration. `frontend/src/api/client.ts` gained `achievementsApi` (replacing the five separate `*Api` objects) and student/faculty category lists (`STUDENT_CATEGORIES`/`FACULTY_CATEGORIES`) driving the unified submit form. As of this writing, the unified-table approach is fully live in both code and production DB — the project owner's initial "revert to separate tables" request in team chat has not been acted on either way; worth a direct conversation rather than assuming either outcome.
