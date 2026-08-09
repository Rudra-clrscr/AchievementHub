# AchievementHub — Project Context

Working notes for contributors (and future AI sessions) on how this system is actually built, why certain decisions were made, and rules that exist because we already got burned once. This is a technical companion to `README.md` (which is more of a feature pitch, and drifts from the real implementation in places — e.g. it still mentions AWS S3/Firebase and a 5MB compression threshold; neither is accurate, see below).

## Stack (actual)

- **Backend:** FastAPI (Python), SQLAlchemy ORM, Alembic migrations.
- **Database:** PostgreSQL, hosted on Supabase.
- **File storage:** Supabase Storage (not S3/Firebase) — only the public URL is ever persisted in Postgres, never raw file bytes.
- **Backend hosting:** Render, free tier — **0.1 vCPU**, limited RAM. This constraint drives a lot of the compression design (see below): bounded per-request latency and memory matter more than squeezing out the last few KB.
- **Frontend hosting:** Vercel. React + Vite + TypeScript.
- **Auth:** JWT (python-jose), password hashing via passlib.

## Data model: why achievement types are separate tables, not one unified table

`Certificate`, `ResearchPublication`, `Patent`, `Internship`, `EventParticipation` are five distinct tables, not one polymorphic `achievements` table with a JSON metadata blob. This was a deliberate choice, re-affirmed after a teammate tried the unified-table approach on a side branch:

1. **Real, typed columns per type.** A patent has `patent_number`/`filing_date`; a publication has `venue`/`publication_date`; an internship has `start_date`/`end_date`. These stay as real, validated Postgres columns (NOT NULL constraints, correct types) instead of an untyped JSON blob where a missing/malformed field fails silently instead of at insert time.
2. **Indexed queries stay fast.** Filtering/sorting on a real column is a normal index lookup. The same filter against a JSON blob is a JSON-path query — slower, and awkward to index well.
3. **Shared logic already exists without a shared table.** `AchievementMixin` (`backend/app/models.py`) carries the common columns (`owner_type`, `student_id`, `file_url`, `status`, `submitted_at`, `verified_by`, `verified_at`, `is_featured`, `thumbnail_url`), and `build_achievement_router` (`backend/app/achievements.py`) generates the submit → pending → verify endpoints once, reused by all five routers. A unified table wouldn't reduce code further — it would only trade away type safety for no real simplicity gain.
4. **`Certificate` predates the mixin** and still duplicates its columns directly rather than using `AchievementMixin` — a known inconsistency, not a design statement. Fine to fold it into the mixin if anyone's touching that area, just not done yet.

### Incident: don't run schema migrations against production without coordinating first

A teammate prototyped the unified-table approach directly against the **shared production Supabase database**, from a migration that was never pushed to `main`. Result: `patents`, `research_publications`, `internships`, and `event_participations` were dropped, a new empty `achievements` table appeared in their place, and the DB's `alembic_version` ended up stamped at a revision (`ffc0eafda47c`) that doesn't exist in any migration file in this repo. Real submitted data (patents, publications, internships, event participations) was lost — no migration step copied it into the new table.

Rules going forward:
- **Never run `alembic upgrade`/`downgrade` against the shared production database from an unreviewed/unpushed branch.** Coordinate in the team chat first, same as any other prod-affecting change.
- **Keep Alembic history linear.** Two migrations both targeting the same parent revision (this happened with `is_featured` being added twice, once per branch) creates divergent heads that `alembic upgrade head` can't resolve without a merge migration. Check `alembic heads` shows exactly one head before merging a PR that touches `alembic/versions/`.
- If you need to experiment with a schema change, do it against a local/throwaway Postgres instance, not the Supabase project this app's `.env` points at.

## Upload compression (`backend/app/uploads.py`)

Every uploaded file (any type, any size — that's a selling point of the app) is either compressed or stored as-is, then pushed to Supabase Storage; only the URL is persisted. Compression exists because raw files would otherwise bloat both storage and the 0.1 vCPU host's per-request time. Design principles, most non-obvious first:

- **Speed over ratio, deliberately.** The host has 0.1 vCPU. Every knob (WebP `method=1` instead of higher search effort, JPEG for photos instead of WebP, no `optimize=True` on JPEG saves, JPEG draft-mode decoding instead of full-res-then-shrink) was chosen after measuring the actual speed/size tradeoff on this host, not assumed.
- **Content-aware routing.** `_classify_image` buckets each image as `photo` (continuous tone → JPEG, fastest and JPEG's natural domain), `graphic` (flat-color UI/diagrams → WebP, since JPEG rings visibly on flat color/sharp edges), or `text` (near-bilevel scans → WebP/PNG lossless first, since lossy quantization blurs small text). This routing is the reason JPEG isn't used everywhere despite being faster — it would visibly hurt quality on the two other content types.
- **Never store something bigger than what was uploaded.** Every compression path (image, PDF, OOXML) is checked against the original size before being kept; if compression didn't help, the original bytes are used instead. This also applies **per-image** inside PDF/OOXML recompression, not just at the whole-file level — a single image inflating can otherwise hide inside a net-smaller file.
- **PDF recompression has two non-obvious failure modes that were found and fixed the hard way:**
  - `page.replace_image()` (PyMuPDF) always creates a throwaway replacement object internally; if you don't call `page.clean_contents(sanitize=True)` afterward, that throwaway object survives garbage collection as an orphaned-but-referenced duplicate, silently doubling every recompressed image's storage cost. Was live in production before being caught by an unrelated support message (see git log around "duplicating every replaced image").
  - `doc.subset_fonts()` looks like a great, cheap size win in isolation (60%+ off font-heavy synthetic tests) but **silently corrupts Type0/CID-keyed fonts** on real-world files (Illustrator-exported PDF text rendered as disconnected marks, no exception thrown to catch it). Do not re-add font subsetting without rendering and eyeballing real output first — a successful `tobytes()` call proves nothing about whether the text is still readable.
- **Editor round-trip metadata is dead weight.** PDFs from design tools (seen from Adobe Illustrator) can embed the *entire native source file* via `PieceInfo`/`AIPDFPrivateData*`, purely so the tool can reopen it for further editing — no PDF viewer ever reads it. Stripping it is lossless for anyone just viewing the file and can be the single biggest size win on such files (measured: one real file went from 2.43MB to 159KB, zero image/font changes).
- **Bounded, not perfect.** A wall-clock budget (`RECOMPRESS_TIME_BUDGET_SECONDS`) caps total per-file recompression time regardless of page/image count, and the quality ladder stops at three attempts rather than searching for an exact size target. Some large multi-image documents (e.g. a 51-page slide deck) legitimately won't hit the 250–500KB target band without visible quality loss — the ceiling is a target, not a guarantee, and `MIN_PER_IMAGE_BUDGET` exists specifically to stop the code from crushing legibility to chase it.

## Free-tier hosting quirks worth knowing

- Render's free-tier backend spins down when idle and cold-starts on the next request. While booting, requests fail at the network level (no HTTP response at all), which browsers report as a **CORS block** even though CORS itself is configured correctly — there's just no response to carry the headers. The frontend retries network-level failures with backoff (`frontend/src/api/client.ts`) to ride this out transparently; don't chase a reported "CORS error" at face value without first checking whether it's actually this.
