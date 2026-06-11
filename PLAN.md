# JobScout — Build Plan v2

*Replanned 2026-06-10. Supersedes [docs/archive/plan-v1-personal-cli.md](docs/archive/plan-v1-personal-cli.md)
(v1 assumed one user hand-authoring config files; v2 is a reusable app with a UI and
document-driven onboarding). Project root: `~/codebases/jobscout/`.*

## Vision

A self-hostable web app anyone can use:

1. **Give it what you have** — drag in any documents about your background: resume/CV
   PDFs, old cover letters, DOCX, plain-text notes, even screenshots (e.g. of a LinkedIn
   profile). Plus a free-form description of the job you're after — role, places, salary
   expectations, anything, in your own words.
2. **The agent builds your profile** — extracts and merges everything into a structured
   master career profile, asks follow-up questions to fill gaps, and shows it to you for
   confirmation and editing.
3. **Then it hunts** — every morning or on demand: discovers postings across the best
   sources, filters and scores them against your preferences, tailors your resume (+
   cover letter when warranted) per job with a truthfulness audit, and delivers
   ready-to-send packets to a review queue in the UI and (optionally) your private
   Telegram — with per-job one-tap auto-apply for supported ATS systems later.

## Requirements → design mapping

| Requirement | Where it lands |
|---|---|
| Reusable for anyone's background | Multi-profile data model; nothing hardcoded; onboarding builds everything from uploads |
| Inputs = arbitrary docs (PDF/CV, cover letters, text, screenshots) | Ingestion service: Claude multimodal extraction (PDF document blocks, vision for images), provenance-tracked merge |
| UI to attach documents | Web app onboarding wizard (drag-drop multi-file upload) |
| UI input for what job they want (stated or unstated specs, e.g. salary) | Free-form preferences intake → LLM structures it → editable confirmation form; salary inference at scoring time when postings omit it |
| Searches best sources, finds everything | Discovery tiers: aggregator APIs + ATS public endpoints + optional JobSpy |
| Filters by interest | Hard filter + LLM scoring vs preferences |
| Tailors resume / builds cover letter, professional format | Tailoring chain + truthfulness audit + Typst→PDF (DOCX secondary) |
| Apply directly OR send docs + link via private Telegram | UI review queue + Telegram delivery; Phase-8 ATS auto-apply with per-job consent |
| All tokens/keys self-service via UI (Telegram etc.) | Settings page: guided per-profile Telegram bot connect flow; API keys entered & validated in UI, stored locally encrypted, masked after save |
| Auto every morning + manual trigger | In-app scheduler per profile + "Run now" button + Telegram `/run` |

---

## 1. Architecture

**A small web application wrapping the v1 pipeline engine.** The engine stays a
deterministic Python library with LLM judgment steps; the app adds ingestion, UI, and
multi-profile state.

```
┌────────────────────────────  Web UI (React) ─────────────────────────────┐
│ Onboarding wizard · Profile editor · Review queue · Job detail ·         │
│ Ad-hoc tailor · Runs/digests · Settings (Telegram, schedule, caps)       │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ REST + SSE (progress streaming)
┌──────────────────────────────┴───────────────────────────────────────────┐
│ FastAPI backend                                                           │
│  ┌ Ingestion service ── multimodal extract → merge → gap interview        │
│  ├ Preferences service ─ free text → structured prefs → confirm           │
│  ├ Pipeline engine ──── discover → dedupe → filter → score → tailor       │
│  │                      → audit → render (unchanged v1 core, per-profile) │
│  ├ Delivery ─────────── UI inbox (always) + Telegram adapter (optional)   │
│  ├ Scheduler ────────── APScheduler cron per profile + run-now            │
│  └ Apply workers ────── Phase 8, Playwright vs Greenhouse/Lever/Ashby     │
│ SQLite (multi-profile) · file store data/files/{profile}/ · Typst render  │
└───────────────────────────────────────────────────────────────────────────┘
```

Single LLM calls with structured outputs (`messages.parse()` + Pydantic) for every
judgment step — no free-roaming agent loop for the daily sweep. Same rationale as v1:
polling the same sources daily is a cron job; judgment is reserved for parsing,
scoring, tailoring, auditing, and the onboarding interview (the one genuinely
conversational part).

**Stack:** Python 3.12 · FastAPI · SQLite + SQLAlchemy · APScheduler · `anthropic` ·
`python-telegram-bot` · Playwright · Typst (PDF) + pandoc (DOCX) · React (Vite + TS +
Tailwind + shadcn/ui) frontend. Monorepo, engine importable + thin CLI kept for
dev/debug. (Fast-and-ugly alternative: Streamlit v0 — only if you want something
clickable in a day; the React UI is the plan of record.)

**Multi-user posture:** designed multi-profile from day one (every table keyed by
`profile_id`), deployed single-instance/local first, bound to localhost, no auth.
Hosted multi-user (real auth, per-user API keys, isolation) is a deliberate later step —
schema won't need to change.

**Configuration & secrets — fully self-service via the UI:** everything a person needs
to set up lives in the Settings page, not in dotfiles: the per-profile Telegram bot
token (guided connect flow, §6) and instance-level API keys (Anthropic, RapidAPI/
JSearch, Adzuna, Jooble), each entered in the UI and validated live with a test call
before saving. Keys are stored in the local DB encrypted at rest (Fernet, instance key
file under `data/`), masked after save, never returned in full by the API, never
committed. `.env` remains an optional developer override only. Per-profile API keys
(each person pays their own way) is a hosted-mode follow-up the schema already allows.

## 2. UX flows

### A. Onboarding wizard (the new heart of the product)
1. **Create profile** → name.
2. **Upload documents** — drag-drop, multi-file: PDF, DOCX, TXT/MD, PNG/JPG/WebP.
   Each shows parse status as the agent processes it.
3. **Describe your target** — one big free-text box: "what are you looking for —
   role(s), seniority, locations/remote, salary expectations, industries, dealbreakers,
   anything else." Optional paste of example postings they like.
4. **Agent builds** — extraction + merge runs with live progress; then a short
   **gap interview** in a chat panel: targeted questions only where evidence is missing
   or conflicting ("The 2021–2023 role at X has no quantified outcomes — any numbers?",
   "Two documents disagree on your start date at Y — which is right?", "No work-
   authorization info found — what's your status for Canada?").
5. **Confirm** — side-by-side review: structured master profile (editable) +
   structured preferences (editable form: titles, locations, remote, salary floor/
   target, dealbreakers, watchlist companies). Approve → profile is live.

Documents can be added anytime later (Profile page → re-merge updates the profile,
showing a diff for approval).

### B. Daily operate loop
Dashboard shows the **review queue**: one card per shortlisted job — score, two-line
"why you fit", flags, salary (listed or estimated), apply link, packet preview
(PDF inline) — with actions **Applied ✅ · Skip ❌ · Re-tailor 🔁 (with notes) ·
Auto-apply 🚀 (Phase 8)**. Runs page shows each morning's digest + errors. Same cards
mirrored to Telegram if connected; actions in either place sync to the same state.

### C. Ad-hoc tailor
"I found this job myself" — paste a URL or JD text → immediate score + tailored packet
for that one posting. Reuses the exact pipeline tail (score → tailor → audit → render),
so it's nearly free to build and makes the app useful even with discovery off.

## 3. Ingestion & profile builder (new component — design detail)

**Per document:**
- PDF → Claude document block (native PDF understanding; chunk >100 pages; 32MB/request
  limit; Files API upload once, reference across calls).
- Image/screenshot → Claude vision (downscale to ≤2500px long edge client-side).
- DOCX → mammoth/pandoc → markdown → text block. TXT/MD → as-is.
- One extraction call per document → structured `ExtractedFacts` (Pydantic): roles
  (company, title, dates, bullets, metrics), education, skills, certs, projects, links,
  plus document type classification (resume / cover letter / narrative / profile
  screenshot) — cover letters are mined for voice + story material, not just facts.

**Merge:** deterministic entity resolution (same company+overlapping dates → same role)
+ one LLM reconciliation pass. Every fact carries **provenance** (`doc_id`, location).
Conflicts and gaps become interview questions rather than silent guesses.

**Gap interview:** generated from a checklist (missing dates, missing metrics, no
work-auth info, unexplained employment gaps >6mo, skills claimed but unevidenced).
Answers are stored as first-class facts with provenance `interview`.

**Output:** versioned `master_profile` (structured YAML/JSON) + `career_history.md`
(merged narrative). **The tailoring stage may select/reorder/rephrase only from this
corpus — and the truthfulness audit now cites provenance**: every claim in a tailored
resume must trace to a document or an interview answer. This is the guardrail that
makes document-driven onboarding safe rather than hallucination-prone.

## 4. Preferences intake

Free text (+ liked-posting examples) → LLM → structured schema: titles[], seniority,
locations[], remote_stance, salary {floor, target, currency}, industries ±, company
watchlist/blocklist, visa needs, dealbreakers[], soft_preferences[], aggressiveness,
daily caps. Rendered back as an editable form for confirmation; raw text kept and
re-parseable. Editable anytime; changes take effect next run.

## 5. Pipeline engine (carried from v1, now per-profile)

`discover → normalize → dedupe → hard-filter → score → shortlist → tailor + audit →
render → deliver → track`

- **Sources, tiered (verified live June 2026):**
  - Tier 1 aggregator APIs: **JSearch** (RapidAPI — Google-for-Jobs index, carries
    LinkedIn/Indeed/Glassdoor-syndicated posts legitimately), **Adzuna** (free tier,
    salary estimates), **Jooble**; niche boards per field (Remotive/RemoteOK/WWR,
    The Muse, HN Who-is-Hiring via Algolia, USAJobs).
  - Tier 2 ATS public JSON (per-profile watchlist): Greenhouse
    `api.greenhouse.io/v1/boards/{company}/jobs?content=true`, Lever
    `api.lever.co/v0/postings/{company}?mode=json`, Ashby (`includeCompensation=true`),
    SmartRecruiters, Workable. No auth, freshest data.
  - Tier 3 **JobSpy** scraper (LinkedIn/Indeed/Glassdoor direct): shipped, **off by
    default** — ToS risk is the user's call, Tier 1 covers most of it.
- **Dedupe:** canonical URL + fuzzy (company,title,location) + JD simhash vs full
  history; cross-board duplicates collapse with all source links.
- **Scoring:** structured verdict {fit_score 0-100, rationale, matched/missing
  requirements, salary_assessment (estimated when unlisted), dealbreakers, recommend}.
  Prompt-cache layout: instructions + preferences as stable prefix, job after the
  breakpoint. Threshold + top-N/day cap.
- **Tailoring:** JD → ranked requirements + ATS keywords → evidence map vs master
  profile → bullet selection/reorder/rewrite (truth-preserving) → cover letter when
  required / high-score-with-hook / config-always; 250–350 words, specific, no
  boilerplate voice → **audit pass** (provenance-cited) blocks unsupported claims.
- **Render:** Typst → ATS-safe single-column PDF; DOCX via pandoc.
  `{Name}_{Company}_{Role}_Resume.pdf`; ATS lint (keyword coverage, length, no
  tables/graphics).

## 6. Delivery

- **UI review queue** is the source of truth (works with zero external setup).
- **Telegram (optional, per profile, fully self-service from the UI):** each person
  connects their own bot — Settings → "Connect Telegram" walks them through it:
  (1) create a bot with @BotFather (in-UI instructions, ~2 min) and paste the token;
  (2) backend validates it (`getMe`) and starts a listener for it; (3) the user sends
  `/start` to their new bot, the app captures the chat id and binds it to the profile;
  (4) a test message confirms the link. Per-job cards with the same actions as the UI
  (inline buttons), morning digest, error alerts, `/run` command. One listener task per
  connected bot inside the backend process — no extra daemon, nothing to configure
  outside the UI. (A shared instance-wide bot with per-profile deep-links remains a
  config option for a hosted deployment later.)

## 7. Auto-apply policy (unchanged, honest)

- No LinkedIn/Indeed bot-applying (ToS, account bans, CAPTCHAs). Those arrive with
  direct links + your packet ready.
- ATS-hosted forms (Greenhouse/Lever/Ashby) are the safe lane: Playwright fills from
  `standard_answers` (collected in onboarding/Settings: work auth, notice, salary-
  question policy, EEO), attaches packet, screenshots review page, submits **only on
  the per-job 🚀 tap** (config flag for full-auto on whitelisted domains, off by
  default).
- Default human-in-the-loop is also the conversion-quality play: 20-second review beats
  the AI-spam bucket.

## 8. Triggering

| Mode | Mechanism |
|---|---|
| Automatic mornings | APScheduler cron per profile (time configurable in Settings) — app runs as a service (launchd keeps it alive on macOS; Docker later) |
| Manual, UI | "Run now" button (full run or per-source) |
| Manual, phone | `/run` to the Telegram bot |
| Ad-hoc single job | paste URL/JD → instant packet |

Local Mac must be awake for scheduled runs → same migration path as v1: Dockerized
single container → $5 VPS when proven (state = SQLite + `data/files/`, trivially
movable).

## 9. Data model (SQLite, all per-profile)

```
profiles(id, name, created_at, settings_json)            -- schedule, caps, models
documents(id, profile_id, filename, mime, sha256, path, status, extracted_json, uploaded_at)
master_profiles(id, profile_id, version, body_json, narrative_md, built_from_doc_ids, created_at)
interview_qa(id, profile_id, question, answer, asked_at, answered_at)
preferences(id, profile_id, version, raw_text, structured_json, created_at)
jobs(id, profile_id, first_seen_at, sources_json, urls_json, canonical_url,
     company, title, location, remote_type,
     salary_min, salary_max, salary_currency, salary_is_estimate,
     posted_at, jd_text, jd_hash,
     status,    -- discovered|filtered_out|scored|shortlisted|tailored|sent|applied|skipped|expired
     score, score_json, telegram_msg_id, feedback, applied_at, notes)
packets(id, job_id, version, resume_pdf, resume_docx, letter_pdf, audit_json, retailor_notes, created_at)
runs(id, profile_id, kind, started_at, finished_at, stats_json, errors_json)
events(id, job_id, ts, from_status, to_status, meta_json)
telegram_bots(profile_id, bot_token_enc, bot_username, chat_id, status, linked_at)
credentials(id, scope, profile_id, name, value_enc, last_validated_at, updated_at)
           -- scope: instance | profile; encrypted at rest; masked in API responses
```

## 10. Repo layout (this folder)

```
jobscout/
  PLAN.md  README.md  docs/
  backend/
    app/
      main.py  api/        # routers: profiles, documents, interview, preferences,
                           #          jobs, packets, runs, actions, telegram, adhoc
      ingest/              # extract.py (multimodal) merge.py interview.py
      prefs/               # parse.py
      engine/
        sources/           # jsearch.py adzuna.py jooble.py greenhouse.py lever.py
                           # ashby.py hn.py jobspy_source.py (off by default)
        normalize.py dedupe.py filter.py score.py tailor.py audit.py
        render/            # resume.typ letter.typ renderer.py
      delivery/            # inbox.py telegram/ (sender, listener, linking)
      apply/               # phase 8 playwright workers
      scheduler.py db.py models.py llm.py config.py
    cli.py                 # dev/debug entry: ingest, run, tailor --job
    tests/                 # fixture docs & JDs, golden extractions, dedupe cases
  frontend/                # Vite + React + TS + Tailwind + shadcn/ui
    src/pages/             # Onboarding Dashboard JobDetail Profile Settings Runs AdHoc
  data/                    # jobscout.db, files/{profile_id}/{uploads,packets}/  (gitignored)
  .env.example  docker-compose.yml (later)
```

## 11. Models & cost (June 2026 pricing)

| Step | Model | Notes |
|---|---|---|
| Document extraction + merge + interview | Opus 4.8 | one-time per profile; vision + PDF; accuracy matters most here |
| Preferences parsing | Opus 4.8 | tiny |
| Scoring | Opus 4.8 default; Haiku 4.5 config option (~1/5 cost) | structured outputs, cached prefix |
| Tailoring + cover letter + audit | Opus 4.8 | adaptive thinking; master profile in cached prefix |

Per-profile economics: onboarding ingestion (≈10 docs incl. screenshots) **< $1
one-time**; running daily at 50 scored + 10 tailored ≈ **$10–40/mo** (Opus everywhere
~$65/mo worst case; Haiku scoring + caching + optional Batches-API scoring at 50% off
brings it down). Hard per-profile caps in settings. Job APIs: free tiers; JSearch is
the one likely paid plan (~$10–25/mo) at higher volume. Infra $0 local / ~$5 VPS.

## 12. Risks & mitigations (delta from v1)

| Risk | Mitigation |
|---|---|
| Bad extraction from screenshots/odd PDFs | Vision + native-PDF parsing is strong; provenance + confidence per fact; gap interview confirms; user edits final profile before anything is sent anywhere |
| Hallucinated profile content | Facts require provenance (doc or interview answer); tailoring audit cites it; user confirmation gate at onboarding |
| Conflicting documents (old vs new resume) | Recency-weighted merge + explicit conflict questions in interview |
| PII now includes uploaded documents | Local disk per-profile folder, gitignored; localhost-bound server; only Anthropic API sees content; deletable per profile (cascade) |
| DOCX parsing quirks | mammoth → markdown; fall back to pandoc; worst case ask user for PDF |
| Source API breakage | Per-source isolation, recorded fixtures in tests, Telegram/UI error alerts |
| ToS (big-board scraping / auto-apply) | Aggregators by default; JobSpy + auto-apply opt-in, ATS-only, per-job consent |
| Cost runaway | Per-profile daily caps, per-run token accounting in digest |
| Generic-AI cover letters | Specific-hook requirement, banned-phrase list, 🔁 feedback loop |

## 13. Build phases

| # | Phase | Scope | Est. | Done when |
|---|---|---|---|---|
| 0 | Scaffold | Monorepo, FastAPI+React hello, SQLite migrations, profile CRUD, encrypted credentials store + Settings page (enter & validate API keys in UI) | 1d | UI creates a profile; Anthropic key entered via Settings passes a live validation call |
| 1 | Ingestion & profile builder | Upload → multimodal extract → merge → gap interview (chat) → editable profile, versioned | 2–3d | Your real docs (incl. a screenshot) → profile you'd sign off on |
| 2 | Preferences intake | Free text → structured → confirm form; standard answers collection | ½–1d | Round-trips your description faithfully |
| 3 | Discovery | Tier 1+2 sources (keys entered via Settings UI), normalize, dedupe, jobs list in UI, digest | 1–2d | Two consecutive runs: deduped, relevant lists |
| 4 | Scoring | Hard filter + LLM verdicts, ranked review queue with rationales | 1d | You agree with ~80% of top-10 ordering |
| 5 | Tailoring + rendering | Tailor chain, provenance audit, Typst PDF/DOCX, packet preview in UI; ad-hoc tailor page | 2–3d | A packet for a real posting passes your review unedited |
| 6 | Telegram + actions | Guided bot-connect flow in UI (BotFather walkthrough → paste token → auto chat-link → test message), cards w/ buttons, digest, `/run`, 🔁 re-tailor flow, action sync | 1–2d | A fresh profile connects its own bot purely through the UI; full loop from phone |
| 7 | Scheduler + ops | APScheduler, run-now, logs, error alerts, caps, idempotency; launchd service | ½–1d | Unattended morning run lands packets |
| 8 | Auto-apply | standard_answers, Playwright Greenhouse/Lever/Ashby, 🚀 consent, screenshots, whitelist | 2–3d | Test submission against a sandbox posting |
| 9 | Learning loop | Feedback-aware scoring, variant A/B, weekly stats | ongoing | — |

**Total to fully useful (through 7): ~9–13 focused days.** Each phase ships something usable.

## 14. Defaults chosen (flag any)

1. FastAPI + React (Vite/TS/Tailwind/shadcn); engine stays an importable Python lib with a dev CLI.
2. Local single-instance, localhost, no auth; multi-profile schema from day one; hosted multi-user later.
3. Opus 4.8 for all LLM steps to start; Haiku 4.5 scoring as a config switch.
4. UI review queue primary; Telegram optional per profile; human-in-the-loop before any auto-apply.
5. Typst→PDF canonical, DOCX secondary; JobSpy shipped but disabled.
6. SQLite (+ files on disk) until hosted; then Postgres + object storage.
7. All setup self-service in the UI: per-profile Telegram bot, API keys in Settings,
   live validation, encrypted local storage; `.env` only as a developer override.

## 15. To start building (Phase 0–1)

1. Your pile of documents (the messier the better — it's the test case): resume PDF,
   old cover letters, any notes/screenshots.
2. Your target-job description in your own words (becomes the preferences fixture).
3. Free accounts when we hit the relevant phase: RapidAPI/JSearch + Adzuna at Phase 3,
   your own @BotFather bot at Phase 6 — all entered straight into the app's Settings
   UI (which validates them live); no files to edit.
4. Confirmation of §14 defaults — especially the stack choice.

## Sources consulted (2026-06-10)

- JobSpy: https://github.com/speedyapply/JobSpy · https://pypi.org/project/python-jobspy/
- JSearch: https://www.openwebninja.com/api/jsearch · Adzuna: https://developer.adzuna.com/
- Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html
- Ashby public postings API: https://developers.ashbyhq.com/docs/public-job-posting-api
- ATS public-API roundup: https://cavuno.com/blog/ats-platforms-public-job-posting-apis
- Prior art: AIHawk https://github.com/feder-cr/jobs_applier_ai_agent_aihawk ·
  ApplyPilot https://github.com/Pickle-Pixel/ApplyPilot ·
  career-ops https://github.com/santifer/career-ops
- Claude models/pricing/multimodal limits: claude-api skill reference (cached 2026-05-26)
