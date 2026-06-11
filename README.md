# JobScout

A self-hostable job-hunt agent: upload whatever career documents you have, describe the
job you want, and it builds your profile, discovers matching postings every morning,
tailors your resume + cover letter per job, and delivers ready-to-send packets to a
review queue and (optionally) your private Telegram.

Plan of record: [PLAN.md](PLAN.md) · **Status: Phase 7 (scheduler) working — the core
product is complete.** Daily unattended runs (discover → score → tailor → deliver) at a
per-profile time with catch-up after sleep, caps in the UI, launchd service template,
review queue + Telegram delivery (Telegram needs a network that doesn't block it —
see "Moving to another machine"). Remaining optional phases: ATS auto-apply (8),
learning loop (9).

## Run it (dev)

```sh
./dev.sh
```

Then open http://localhost:5173. First run creates the Python venv and installs npm
packages automatically (needs Python ≥ 3.11 and Node ≥ 18).

Manual equivalent:

```sh
# backend (http://127.0.0.1:8000)
cd backend
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

## First-time setup (all in the UI)

1. Open Settings → paste your Anthropic API key → it validates live against the API.
2. Create your profile on the Profiles page.
3. (Phase 3+) job-source API keys; (Phase 6) Telegram bot — all entered in Settings too.

Secrets are encrypted at rest (key file in `data/secret.key`, auto-generated, never
committed) and masked everywhere after save. `data/` holds the SQLite DB and uploaded
files and is gitignored.

## Run as a background service (launchd)

The daily scheduler only fires while the app is running. To run it unattended (no
terminal), serve the built frontend from the backend on one port and let launchd keep
it alive:

```sh
cd frontend && npm run build && cd ..          # backend serves dist/ at :8000
sed "s|__REPO__|$(pwd)|g" ops/com.jobscout.plist > ~/Library/LaunchAgents/com.jobscout.plist
launchctl load ~/Library/LaunchAgents/com.jobscout.plist
open http://localhost:8000
```

Stop with `launchctl unload ~/Library/LaunchAgents/com.jobscout.plist`. Logs land in
`data/jobscout.log`. (Don't run `./dev.sh` and the service at the same time — they
both want port 8000.)

## Moving to another machine

The repo alone is not enough — three things live outside it:

1. **`data/` directory** (gitignored): the SQLite DB (profiles, jobs, packets),
   `secret.key` (without it the encrypted API keys cannot be decrypted), uploaded
   documents, and generated PDFs. Copy it to the same place in the new checkout —
   or skip it and just re-onboard (re-upload documents, re-paste keys; ~15 min).
2. **Toolchain**: Python ≥ 3.11, Node ≥ 18, and **Typst** (`brew install typst` —
   PDF rendering breaks without it). `./dev.sh` rebuilds the venv and node_modules
   itself on first run; never copy `.venv/` or `node_modules/` between machines.
3. Then just `./dev.sh`. On a machine without a TLS-intercepting proxy, Telegram
   delivery works immediately (it's blocked on corporate networks like Zscaler).

## Layout

```
backend/   FastAPI app — API, DB (SQLite + Alembic), engine, Telegram, scheduler
frontend/  React + Vite + Tailwind UI
data/      runtime state (gitignored)
ops/       launchd service template
docs/      plans and notes
```
