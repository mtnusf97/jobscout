# JobScout — Personal Job-Hunt Agent: Build Plan

*Drafted 2026-06-10. Working name "JobScout" — rename freely.*

## What it does

Every morning (or on demand), JobScout discovers new job postings matching your spec,
scores them against your preferences, tailors your resume (+ cover letter when warranted)
for the best ones, and delivers ready-to-send application packets to a private Telegram
channel — with optional one-tap auto-apply for supported ATS systems.

## Requirements → design mapping

| Your requirement | Where it lands |
|---|---|
| Takes a job spec (role, location, salary — stated or not) | `profile/preferences.md` + salary-inference in scoring |
| Takes base resume + full career/education history | `profile/master_resume.yaml` + `profile/career_history.md` |
| Searches all the best sources, finds everything | Discovery tiers (aggregator APIs + ATS endpoints + JobSpy) |
| Filters by what I'm interested in | Hard filter + LLM scoring against preferences |
| Tailors resume, builds cover letter when needed, professional format | Tailoring chain + truthfulness audit + Typst/PDF render |
| Applies directly OR sends docs + link to private Telegram | Telegram delivery (default) + per-job consent auto-apply (Phase 6) |
| Triggered automatically every morning or manually | launchd/cron schedule + CLI + Telegram `/run` command |

---

## 1. Core architecture decision

**Hybrid: deterministic pipeline skeleton, LLM judgment steps.**

- **Plain Python** handles fetching, normalization, dedup, state, rendering, Telegram —
  boring, reliable, cheap, debuggable, testable.
- **Claude API** handles judgment: JD parsing, relevance scoring, resume tailoring,
  cover letters, truthfulness auditing. Single `messages` calls with structured outputs
  (`client.messages.parse()` + Pydantic) — not agent loops.
- **Playwright browser automation** only where there's no API: odd career pages, and the
  optional auto-apply worker.

Why not one big end-to-end agent that "browses the web like a human" every morning:
the same sources get polled every day — that's a cron job, not a research problem.
Agentic improvisation is slower, costlier, and flakier for repeated structured work.
Agent-style behavior is reserved for the steps that genuinely need judgment.

This matches how the successful prior art is built (AIHawk, ApplyPilot, career-ops —
see §13).

## 2. Inputs — two artifacts you own and edit anytime

### `profile/preferences.md`
Target titles + seniority; locations and remote stance; **salary floor and target**
(used even when postings don't state salary — see scoring); industries/companies to
favor or avoid; visa/work-authorization needs; dealbreakers ("no on-site 5 days",
"no crypto"); soft preferences ("small teams", "ML-adjacent ok"); filter aggressiveness;
daily caps.

### `profile/master_resume.yaml` + `profile/career_history.md`
The **superset resume**: every role with many bullets (more than fit on one page), each
achievement with metrics, full skills taxonomy, education, certs, projects, links —
structured YAML so the tailor can select and reorder programmatically. The companion
`career_history.md` is free-form narrative (stories, context, numbers) the LLM can mine
for cover letters and for rephrasing bullets.

**This is the single source of truth. The tailor may select, reorder, and rephrase from
it — never invent.** Built once from your current resume + a short Q&A session with me.

### `config.yaml` + `.env`
Sources on/off, target-company watchlist, model choices, caps, schedule time, Telegram
chat id. Secrets (API keys, bot token) in `.env`, never committed.

## 3. Pipeline (one run, idempotent)

```
discover → normalize → dedupe → hard-filter → score (LLM) → shortlist
        → tailor + audit (LLM) → render (PDF/DOCX) → deliver (Telegram) → track (SQLite)
```

1. **Discover** — pull postings new since last run from every enabled source (first run
   backfills ~14 days). Each source is an isolated module; one failing source never
   kills the run.
2. **Normalize** — map everything to one canonical `Job` schema (§9).
3. **Dedupe** — canonical-URL match + fuzzy (company, title, location) hash + JD-text
   simhash, checked against the whole history DB. The same role syndicated across boards
   collapses into one record carrying all source links.
4. **Hard filter** (no LLM, free) — location/remote, posted-date window, title
   include/exclude keywords, salary floor *when stated*, language. Cuts ~200/day to ~40.
5. **Score** (LLM, structured output) — job + preferences → `{fit_score 0-100, rationale,
   matched_requirements[], missing_requirements[], salary_assessment, dealbreakers[],
   recommend: apply|maybe|skip}`. When salary is unlisted, the model estimates a range
   from title/company/location/market and flags it `estimated`. Threshold + daily top-N
   cap (default 10) decide what proceeds.
6. **Tailor** (LLM, strong model) — per shortlisted job:
   a. Parse JD into ranked requirements and ATS keywords.
   b. Map each requirement to evidence in the master profile.
   c. Select + order sections/bullets; rephrase bullets using JD vocabulary
      (truth-preserving rewrite only).
   d. Cover letter when (i) the application requires one, (ii) score is high and there's
      a strong specific hook, or (iii) config says always. 250–350 words, specific, no
      LLM-boilerplate voice.
   e. **Truthfulness audit** — a second LLM pass diffs every claim in the tailored output
      against the master profile; any unsupported claim blocks the packet and gets
      rewritten. This is the guardrail that makes aggressive tailoring safe.
7. **Render** — Typst template → ATS-safe single-column PDF (+ DOCX via pandoc when a
   form wants it). Consistent header/typography across resume and letter.
   `Matin_Yousefabadi_{Company}_{Role}_Resume.pdf`. ATS lint: keyword coverage check,
   1–2 pages, no tables/graphics/text-boxes, standard fonts.
8. **Deliver** — Telegram (§6).
9. **Track** — every job and state transition recorded in SQLite (§9); feedback from
   Telegram buttons flows back in.

## 4. Sources (tiered, API-first)

**Tier 1 — aggregator APIs (legit, stable, cover the big boards indirectly):**
- **JSearch** (RapidAPI / OpenWeb Ninja) — effectively the Google-for-Jobs index, which
  syndicates LinkedIn/Indeed/Glassdoor/company postings. Primary aggregator.
- **Adzuna** (`developer.adzuna.com`) — free tier, salary data + salary *estimates*.
- **Jooble API** — free key on request, broad coverage.
- Niche per your field: Remotive / RemoteOK / WeWorkRemotely (remote roles), The Muse,
  HN "Who is Hiring" via Algolia API, USAJobs (if US-gov relevant).

**Tier 2 — ATS public JSON endpoints for a target-company watchlist (highest value):**
- Greenhouse: `GET https://api.greenhouse.io/v1/boards/{company}/jobs?content=true`
- Lever: `GET https://api.lever.co/v0/postings/{company}?mode=json`
- Ashby: public Job Postings API (`includeCompensation=true` gives salary!)
- SmartRecruiters, Workable: similar public feeds.
- No auth, no scraping, fresh data — postings appear here before they hit boards. You
  maintain `watchlist.yaml` of companies you care about; the agent polls all daily and
  can auto-discover which ATS a company uses.

**Tier 3 — JobSpy scraper (optional, off by default):**
- `python-jobspy` scrapes LinkedIn/Indeed/Glassdoor/ZipRecruiter/Google directly in one
  call, no login. Actively maintained (PyPI release 2026-05). Caveats: scraping those
  boards violates their ToS and breaks occasionally; Tier 1 already covers most of the
  same postings legitimately. Ship the module, leave it disabled; you flip the flag.

Dedup (§3.3) makes cross-tier overlap harmless. "Finds everything" honestly means:
daily incremental sweep across all enabled sources + first-run backfill — not literally
every posting on the internet, but everything these sources surface for your query set.

## 5. Scoring design

- Prompt = preferences file + canonical job record (title, company, location, salary,
  full JD text). Structured output via Pydantic schema (validated, no parsing bugs).
- **Prompt-caching layout:** static instructions + preferences first under a
  `cache_control` breakpoint; per-job content after it. Within a run, calls 2..N read
  the cached prefix (~0.1× input price).
- Two-step option later: embedding pre-rank if daily volume gets large (skip for v1).
- Feedback loop (Phase 7): jobs you marked ❌/✅ become few-shot signals appended to the
  scoring prompt ("user skipped these, applied to these").

## 6. Delivery — Telegram

Setup (one-time, ~5 min): create bot via @BotFather → token; create the private channel
and add the bot as admin — or simpler, use a **direct private chat with the bot** (inline
buttons behave best there; channel also works if you prefer).

**Per-job message:**
```
🎯 87/100 — Senior ML Engineer @ FooAI
📍 Toronto (hybrid 2d) · 💰 $170–200k CAD (listed)
Why: 6 yrs Python/ML matches core stack; their RAG roadmap maps directly
to your X project. Missing: production K8s (addressed in resume framing).
⚠️ Posted 9 days ago — apply soon.
📎 Resume PDF + cover letter attached · [Apply ↗](link)
[✅ Applied] [❌ Skip] [🔁 Re-tailor] [🚀 Auto-apply]
```
+ documents via `sendDocument`, + one morning digest message (run summary: N found,
M scored, K packets, errors if any).

**Buttons (inline keyboard callbacks):**
- ✅ Applied / ❌ Skip → state + feedback DB.
- 🔁 Re-tailor → reply with notes ("emphasize leadership") → regenerates packet.
- 🚀 Auto-apply → Phase 6, whitelisted ATS only, per-job consent by design.

**Listener:** a tiny long-running poller (launchd-managed, `getUpdates`) handles buttons
and commands instantly, including **`/run` from your phone** — your "whenever I feel
like it" manual trigger. Degraded mode without the daemon: pending button presses are
ingested at the start of the next scheduled run.

## 7. Auto-apply policy (the honest part)

- **LinkedIn / Indeed "Easy Apply" bots:** violate ToS, account-ban risk, CAPTCHAs.
  Not building that. Those postings arrive via Tier 1 with a direct link — you tap it
  with the tailored PDF already in hand.
- **ATS-hosted forms (Greenhouse/Lever/Ashby):** plain web forms, not account-bound,
  usually no CAPTCHA — safe lane for automation. Phase 6 Playwright worker fills them
  using `profile/standard_answers.yaml` (work auth, notice period, salary-question
  policy, EEO answers), attaches the packet, screenshots the review page, and submits
  **only after your 🚀 tap on that specific job** (or, if you later enable it, a config
  flag for fully-automatic on whitelisted domains).
- Quality argument for human-in-the-loop default: a 20-second review catches tailoring
  misses and keeps you out of the AI-spam bucket recruiters increasingly filter; volume
  isn't the bottleneck, conversion is.

## 8. Triggering

| Mode | Mechanism |
|---|---|
| Every morning | macOS **launchd** plist (better than cron across sleep/wake), e.g. 07:30 |
| Manual, terminal | `jobscout run` (`--dry-run`, `--source jsearch`, `--max 5`, `--retailor <id> "notes"`) |
| Manual, phone | `/run` to the Telegram bot |
| From Claude Code | optional scheduled routine wrapping the CLI, so I can run/triage it in chat |

Caveat: local schedule requires the Mac to be awake. When proven, lift to a $5 VPS or
GitHub Actions cron (repo private, secrets in Actions) — the pipeline is stateless apart
from SQLite + profile files, so the move is trivial. Start local.

## 9. Data model (SQLite)

```
jobs(
  id, first_seen_at, sources_json, urls_json, canonical_url,
  company, title, location, remote_type,
  salary_min, salary_max, salary_currency, salary_is_estimate,
  posted_at, jd_text, jd_hash,
  status,           -- discovered | filtered_out | scored | shortlisted
                    -- | tailored | sent | applied | skipped | expired
  score, score_json,            -- full structured verdict
  packet_dir, telegram_msg_id,
  feedback, applied_at, notes
)
runs(id, started_at, finished_at, stats_json, errors_json)
events(job_id, ts, from_status, to_status, meta)   -- audit trail
```

## 10. Repo layout

```
jobscout/
  config.yaml  .env
  profile/
    preferences.md  master_resume.yaml  career_history.md
    standard_answers.yaml          # phase 6
    watchlist.yaml                 # tier-2 target companies
  jobscout/
    sources/      # jsearch.py adzuna.py jooble.py greenhouse.py lever.py
                  # ashby.py hn.py jobspy_source.py (off by default)
    normalize.py  dedupe.py  filter.py
    score.py      # Claude structured-output call
    tailor.py     # JD parse → evidence map → rewrite → letter → audit
    render/       # resume.typ letter.typ + renderer; pandoc docx fallback
    telegram/     # sender.py listener.py (poller daemon)
    apply/        # phase 6 playwright workers (greenhouse.py lever.py ashby.py)
    db.py  models.py  run.py      # orchestrator + CLI (typer)
  data/jobscout.db
  out/2026-06-10/FooAI_Senior_ML_Engineer/   # rendered packets
  logs/
  tests/          # fixture JDs, golden tailoring cases, dedupe cases
```

Stack: Python 3.12, `httpx`, `pydantic`, `typer`, `anthropic`, `python-telegram-bot`,
`playwright`, Typst (binary) for PDF, `pandoc` for DOCX, SQLite. All swappable if you
prefer TypeScript — say so before Phase 1.

## 11. Models & cost (June 2026 pricing)

| Step | Default model | Config alternative |
|---|---|---|
| Scoring/classification | Opus 4.8 (`claude-opus-4-8`) for best judgment | Haiku 4.5 (`claude-haiku-4-5`) at ~1/5 the cost once you trust the rubric |
| JD parsing + tailoring + cover letter + audit | Opus 4.8 | Sonnet 4.6 middle ground |

All calls: structured outputs (`messages.parse()` + Pydantic), adaptive thinking on
tailoring/audit, prompt caching (stable prefix = instructions + preferences/master
profile; per-job content after the breakpoint).

Rough monthly cost at heavy daily use (50 scored + 10 tailored every day):
- Scoring: Opus ≈ $30/mo · Haiku ≈ $6/mo (less with caching)
- Tailoring + audit: Opus ≈ $35/mo (cache reads make the master-profile tokens ~0.1×)
- Optional: run scoring through the **Batches API** (50% off) since the morning run can
  tolerate ~30 min latency — start the batch before your wake-up time.
- Job APIs: free tiers (JSearch limited free reqs/mo — the one likely paid upgrade,
  ~$10–25/mo if you want deep daily volume; Adzuna/Jooble/ATS/Telegram free).
- Infra: $0 local; ~$5/mo if moved to a VPS.

Realistic total: **$10–40/mo** moderate use; hard daily caps in config prevent runaway.

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Source API breaks/changes | Per-source isolation; run continues; error alert to Telegram; tests with recorded fixtures |
| Duplicate/ghost/reposted jobs | History-DB dedupe, posted-date window, repost detection (same jd_hash reappearing) |
| Fabricated resume content | Master-profile-only rule + adversarial audit pass + human review before send (default) |
| ToS / account bans | Big boards via aggregators; JobSpy off by default; auto-apply only on ATS forms with per-job consent |
| Generic AI cover letters hurting conversion | Specific-hook requirement, banned-phrase list, your 🔁 feedback loop |
| PII leakage | Everything local / private repo; resume text goes only to Anthropic API; secrets in .env; private chat |
| Cost runaway | Daily caps on scored + tailored counts; per-run token log in digest |
| Laptop asleep at 07:30 | launchd (runs on wake) → later VPS/Actions |

## 13. Prior art (validation + parts to borrow)

- **JobSpy** (`python-jobspy`) — maintained scraper lib, Tier 3 module.
- **AIHawk / Jobs_Applier_AI_Agent** — popular LinkedIn auto-applier; proves demand,
  also proves the ban-risk pain we're avoiding.
- **ApplyPilot** (2026) — open-source full-loop applier (discover→score→tailor→submit);
  similar architecture to this plan, validates feasibility.
- **career-ops** — job-search system built on Claude Code; ideas for skill-mode UX.
We build custom because none combine: truthful-tailoring audit, Telegram
review-and-approve flow, ATS-watchlist sourcing, and your exact preference model.

## 14. Build phases (each independently useful)

- **Phase 0 — setup** (½ day): repo scaffold, .env, BotFather bot + chat id, RapidAPI +
  Adzuna keys, draft profile files from your current resume (short Q&A with you).
  *Done when: `jobscout hello` posts a test message + doc to your Telegram.*
- **Phase 1 — discovery loop** (1–2 days): Tier 1 + Tier 2 sources → normalize → dedupe
  → SQLite → morning digest with raw links. *Done when: two consecutive mornings produce
  non-overlapping, deduped, relevant-looking lists.*
- **Phase 2 — scoring** (1 day): hard filter + LLM scoring + thresholds; digest becomes
  ranked with rationales. *Done when: you agree with ~80% of its top-10 ordering.*
- **Phase 3 — tailoring + rendering** (2–3 days, the heart): master profile finalized,
  Typst templates, tailoring chain, truthfulness audit, cover letters, PDF/DOCX.
  *Done when: a packet for a real posting passes your own review without edits.*
- **Phase 4 — full delivery** (1 day): per-job messages w/ attachments, inline buttons,
  listener daemon, `/run`, 🔁 re-tailor flow.
- **Phase 5 — ops hardening** (½ day): launchd schedule, structured logs, Telegram error
  alerts, idempotent re-runs, cost caps, (optional) batch-mode scoring.
- **Phase 6 — auto-apply** (2–3 days incl. careful testing): standard_answers.yaml,
  Playwright workers for Greenhouse/Lever/Ashby, 🚀 consent flow, confirmation
  screenshots, domain whitelist.
- **Phase 7 — learning loop** (ongoing): feedback-informed scoring, resume-variant A/B,
  weekly stats (sent → applied → responses).

Total to a fully useful system (through Phase 5): **~6–8 focused days**. Auto-apply +2–3.

## 15. Defaults I chose (flag if you disagree)

1. Python stack (vs TypeScript).
2. Opus 4.8 everywhere to start; Haiku option for scoring exposed in config.
3. Human-in-the-loop delivery first; auto-apply later, per-job consent, ATS-only.
4. Local Mac + launchd first; cloud later.
5. Typst→PDF as the canonical format, DOCX secondary.
6. JobSpy module shipped but disabled (ToS call is yours).
7. Telegram: private chat with bot recommended over channel (buttons UX); channel works too.

## 16. What I need from you before Phase 0

1. Current resume (any format) + brain-dump of career history — or 20 min of Q&A.
2. The actual preferences: titles, locations, remote stance, salary floor/target,
   dealbreakers, target-company list (optional but high-value).
3. Telegram: create the bot via @BotFather (2 min), send the token; your chat id.
4. Free signups: RapidAPI key (JSearch) + Adzuna app id/key (+ Jooble if wanted).
5. Confirmation on the defaults in §15.

## Sources consulted (2026-06-10)

- JobSpy: https://github.com/speedyapply/JobSpy · https://pypi.org/project/python-jobspy/
- JSearch: https://www.openwebninja.com/api/jsearch · Adzuna: https://developer.adzuna.com/
- Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html
- Ashby public postings API: https://developers.ashbyhq.com/docs/public-job-posting-api
- ATS public-API roundup: https://cavuno.com/blog/ats-platforms-public-job-posting-apis
- AIHawk: https://github.com/feder-cr/jobs_applier_ai_agent_aihawk ·
  ApplyPilot: https://github.com/Pickle-Pixel/ApplyPilot ·
  career-ops: https://github.com/santifer/career-ops
- Claude models/pricing: claude-api skill reference (cached 2026-05-26)
