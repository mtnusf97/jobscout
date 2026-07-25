import {
  AlarmClock,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  Hammer,
  MessageCircleQuestion,
  Radar,
  RotateCcw,
  Save,
  Send,
  Sparkles,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Input, Select, Spinner } from "../components/ui";
import {
  api,
  ApiError,
  type DocumentItem,
  type MasterBody,
  type MasterProfileOut,
  type OnboardingStatus,
  type PBullet,
  type PreferencesOut,
  type Profile,
  type QuestionItem,
  type RunOut,
  type TelegramState,
} from "../lib/api";

// Keep in sync with ALLOWED_MODELS in backend/app/llm.py
const MODEL_OPTIONS = [
  { value: "claude-haiku-4-5", label: "Haiku 4.5 — cheapest" },
  { value: "claude-sonnet-5", label: "Sonnet 5 — balanced (newest)" },
  { value: "claude-opus-4-8", label: "Opus 4.8 — high quality" },
  { value: "claude-opus-5", label: "Opus 5 — most capable (newest)" },
] as const;
const DEFAULT_MODEL_SCORE = "claude-haiku-4-5";
const DEFAULT_MODEL_TAILOR = "claude-sonnet-5";

function ModelSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-sm text-zinc-700">
      <span className="mb-1 block text-xs text-zinc-400">{label}</span>
      <Select className="w-44" value={value} onChange={(e) => onChange(e.target.value)}>
        {MODEL_OPTIONS.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </Select>
    </label>
  );
}

function SourceChips({
  ids,
  builtFrom,
}: {
  ids: string[];
  builtFrom: Record<string, { filename: string }>;
}) {
  if (!ids || ids.length === 0) return null;
  return (
    <span className="ml-1.5 inline-flex gap-1 align-middle">
      {ids.map((alias) => (
        <span
          key={alias}
          title={alias === "interview" ? "From your interview answer" : builtFrom[alias]?.filename ?? alias}
          className="rounded bg-zinc-100 px-1 text-[10px] font-medium text-zinc-400"
        >
          {alias === "interview" ? "you" : alias}
        </span>
      ))}
    </span>
  );
}

function Bullets({
  bullets,
  builtFrom,
}: {
  bullets: PBullet[];
  builtFrom: Record<string, { filename: string }>;
}) {
  return (
    <ul className="mt-1.5 space-y-1">
      {bullets.map((b, i) => (
        <li key={i} className="text-sm leading-snug text-zinc-700">
          • {b.text}
          <SourceChips ids={b.source_doc_ids} builtFrom={builtFrom} />
        </li>
      ))}
    </ul>
  );
}

function DocStatus({ doc }: { doc: DocumentItem }) {
  if (doc.status === "extracted")
    return <Badge tone="green">{doc.doc_type ?? "extracted"}</Badge>;
  if (doc.status === "failed") return <Badge tone="red">failed</Badge>;
  if (doc.status === "processing")
    return (
      <Badge tone="indigo">
        <Spinner className="h-3 w-3" /> extracting
      </Badge>
    );
  return <Badge tone="zinc">queued</Badge>;
}

export default function ProfileDetail() {
  const params = useParams<{ id: string }>();
  const pid = params.id ?? "";

  const [profile, setProfile] = useState<Profile | null>(null);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [onb, setOnb] = useState<OnboardingStatus>({ status: "idle" });
  const [mp, setMp] = useState<MasterProfileOut | null>(null);
  const [questions, setQuestions] = useState<QuestionItem[]>([]);
  const [pageError, setPageError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [note, setNote] = useState("");
  const [editJson, setEditJson] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<PreferencesOut | null>(null);
  const [prefsText, setPrefsText] = useState("");
  const [prefsBusy, setPrefsBusy] = useState(false);
  const [prefsJson, setPrefsJson] = useState<string | null>(null);
  const [latestRun, setLatestRun] = useState<RunOut | null>(null);
  const [tg, setTg] = useState<TelegramState | null>(null);
  const [tgToken, setTgToken] = useState("");
  const [tgBusy, setTgBusy] = useState(false);
  const [tgMsg, setTgMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedTime, setSchedTime] = useState("08:00");
  const [capScore, setCapScore] = useState(80);
  const [capTailor, setCapTailor] = useState(5);
  const [modelScore, setModelScore] = useState<string>(DEFAULT_MODEL_SCORE);
  const [modelTailor, setModelTailor] = useState<string>(DEFAULT_MODEL_TAILOR);
  const [design, setDesign] = useState("");
  const [designMsg, setDesignMsg] = useState<string | null>(null);
  const [pages, setPages] = useState(1); // 1 | 2 | 0 (no limit)
  const [schedLoaded, setSchedLoaded] = useState(false);
  const [schedMsg, setSchedMsg] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    if (!pid) return;
    try {
      const [p, d, o, q, r, t] = await Promise.all([
        api.get<Profile>(`/profiles/${pid}`),
        api.get<DocumentItem[]>(`/profiles/${pid}/documents`),
        api.get<OnboardingStatus>(`/profiles/${pid}/onboarding`),
        api.get<QuestionItem[]>(`/profiles/${pid}/questions`),
        api.get<RunOut[]>(`/profiles/${pid}/runs`),
        api.get<TelegramState>(`/profiles/${pid}/telegram`),
      ]);
      setProfile(p);
      setDocs(d);
      setOnb(o);
      setQuestions(q);
      setLatestRun(r[0] ?? null);
      setTg(t);
      try {
        setMp(await api.get<MasterProfileOut>(`/profiles/${pid}/profile`));
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) setMp(null);
        else throw e;
      }
      try {
        setPrefs(await api.get<PreferencesOut>(`/profiles/${pid}/preferences`));
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) setPrefs(null);
        else throw e;
      }
      setPageError(null);
    } catch (e) {
      setPageError((e as Error).message);
    }
  }, [pid]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (prefs && prefsText === "") setPrefsText(prefs.raw_text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs]);

  useEffect(() => {
    if (!profile || schedLoaded) return;
    const schedule = (profile.settings.schedule ?? {}) as { enabled?: boolean; time?: string };
    const caps = (profile.settings.caps ?? {}) as {
      score_per_run?: number;
      tailor_per_run?: number;
    };
    const modelsSel = (profile.settings.models ?? {}) as {
      scoring?: string;
      tailoring?: string;
    };
    setSchedEnabled(Boolean(schedule.enabled));
    setSchedTime(schedule.time ?? "08:00");
    setCapScore(caps.score_per_run ?? 80);
    setCapTailor(caps.tailor_per_run ?? 5);
    setModelScore(modelsSel.scoring ?? DEFAULT_MODEL_SCORE);
    setModelTailor(modelsSel.tailoring ?? DEFAULT_MODEL_TAILOR);
    setDesign((profile.settings.resume_design as string) ?? "");
    setPages((profile.settings.resume_pages as number) ?? 1);
    setSchedLoaded(true);
  }, [profile, schedLoaded]);

  async function saveSchedule() {
    if (!profile) return;
    setSchedMsg(null);
    const previous = (profile.settings.schedule ?? {}) as Record<string, unknown>;
    await act(() =>
      api.patch(`/profiles/${pid}`, {
        settings: {
          ...profile.settings,
          schedule: { ...previous, enabled: schedEnabled, time: schedTime },
          caps: { score_per_run: capScore, tailor_per_run: capTailor },
          models: { scoring: modelScore, tailoring: modelTailor },
        },
      }),
    );
    setSchedMsg("Saved.");
  }

  // Persist model choices on their own (used by the dropdowns in the Discovery card,
  // which have no Save button — a run reads these from the saved profile settings).
  async function persistModels(scoring: string, tailoring: string) {
    if (!profile) return;
    await act(() =>
      api.patch(`/profiles/${pid}`, {
        settings: { ...profile.settings, models: { scoring, tailoring } },
      }),
    );
  }

  async function saveDesign() {
    if (!profile) return;
    setDesignMsg(null);
    await act(() =>
      api.patch(`/profiles/${pid}`, {
        settings: { ...profile.settings, resume_design: design, resume_pages: pages },
      }),
    );
    setDesignMsg("Saved.");
  }

  const docsBusy = docs.some((d) => d.status === "uploaded" || d.status === "processing");
  const llmBusy = onb.status === "building" || onb.status === "refining";
  const runBusy = latestRun?.status === "running";
  const tgPending = tg?.status === "pending";

  useEffect(() => {
    if (!docsBusy && !llmBusy && !runBusy && !tgPending) return;
    const timer = setInterval(() => void refresh(), 2500);
    return () => clearInterval(timer);
  }, [docsBusy, llmBusy, runBusy, tgPending, refresh]);

  async function act(fn: () => Promise<unknown>) {
    setActionError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  async function onFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    setUploading(true);
    await act(() => api.upload(`/profiles/${pid}/documents`, Array.from(list)));
    setUploading(false);
    if (fileInput.current) fileInput.current.value = "";
  }

  const runDisc = latestRun ? (latestRun.stats.discovery ?? latestRun.stats) : null;
  const runScor = latestRun?.stats.scoring ?? null;
  const runTail = latestRun?.stats.tailoring ?? null;
  const extractedCount = docs.filter((d) => d.status === "extracted").length;
  const openQs = questions.filter((q) => q.status === "open");
  const answeredQs = questions.filter((q) => q.status === "answered");
  const appliedQs = questions.filter((q) => q.status === "applied");
  const builtFrom = mp?.built_from ?? {};
  const body: MasterBody | null = mp?.body ?? null;

  if (!profile) {
    return (
      <div className="flex justify-center py-24 text-zinc-400">
        {pageError ? <p className="text-sm text-red-600">{pageError}</p> : <Spinner className="h-6 w-6" />}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/profiles" className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600">
          <ArrowLeft className="h-3 w-3" /> all profiles
        </Link>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">{profile.name}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Onboarding: upload career documents, build the master profile, answer the gap interview.
        </p>
      </div>

      {(actionError || onb.status === "failed") && (
        <Card className="border-red-200 bg-red-50/40">
          <CardBody className="text-sm text-red-700">
            {actionError ?? `Last run failed: ${onb.error ?? "unknown error"}`}
          </CardBody>
        </Card>
      )}

      {/* 1 — documents */}
      <Card
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          void onFiles(e.dataTransfer.files);
        }}
      >
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>1 · Documents</CardTitle>
          <Button onClick={() => fileInput.current?.click()} disabled={uploading}>
            {uploading ? <Spinner /> : <Upload className="h-4 w-4" />} Add files
          </Button>
        </CardHeader>
        <CardBody>
          <input
            ref={fileInput}
            type="file"
            multiple
            className="hidden"
            accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,.gif"
            onChange={(e) => void onFiles(e.target.files)}
          />
          <p className="text-xs text-zinc-400">
            Drag &amp; drop anywhere on this card — resume/CV PDFs, old cover letters, notes, screenshots.
          </p>
          {docs.length > 0 && (
            <ul className="mt-3 divide-y divide-zinc-100">
              {docs.map((doc) => (
                <li key={doc.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="flex min-w-0 items-center gap-2.5">
                    <FileText className="h-4 w-4 shrink-0 text-zinc-300" />
                    <div className="min-w-0">
                      <div className="truncate text-sm text-zinc-800">{doc.filename}</div>
                      {doc.error && <div className="text-xs text-red-600">{doc.error}</div>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <DocStatus doc={doc} />
                    {doc.status === "failed" && (
                      <Button
                        variant="outline"
                        title="Retry extraction"
                        onClick={() =>
                          void act(() => api.post(`/profiles/${pid}/documents/${doc.id}/retry`))
                        }
                      >
                        <RotateCcw className="h-4 w-4" /> Retry
                      </Button>
                    )}
                    <Button
                      variant="danger"
                      title="Remove"
                      onClick={() => void act(() => api.del(`/profiles/${pid}/documents/${doc.id}`))}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      {/* 2 — build */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>2 · Master profile</CardTitle>
          <div className="flex items-center gap-2">
            {mp && (
              <span className="text-xs text-zinc-400">
                v{mp.version} · {mp.origin} · {new Date(mp.created_at).toLocaleString()}
              </span>
            )}
            <Button
              onClick={() => void act(() => api.post(`/profiles/${pid}/build`))}
              disabled={extractedCount === 0 || llmBusy || docsBusy}
            >
              {llmBusy ? <Spinner /> : <Hammer className="h-4 w-4" />}
              {onb.status === "building"
                ? "Building…"
                : onb.status === "refining"
                  ? "Refining…"
                  : mp
                    ? "Rebuild from documents"
                    : "Build profile"}
            </Button>
          </div>
        </CardHeader>
        <CardBody>
          {!mp && !llmBusy && (
            <p className="text-sm text-zinc-400">
              {extractedCount === 0
                ? "Waiting for at least one extracted document."
                : `${extractedCount} document(s) ready — hit Build.`}
            </p>
          )}
          {llmBusy && (
            <p className="flex items-center gap-2 text-sm text-zinc-500">
              <Spinner /> The agent is {onb.status} the profile — usually under a minute.
            </p>
          )}
          {body && !llmBusy && (
            <div className="space-y-5">
              <div>
                <div className="text-lg font-semibold">{body.full_name ?? profile.name}</div>
                {body.headline && <div className="text-sm text-zinc-600">{body.headline}</div>}
                <div className="mt-1 text-xs text-zinc-400">
                  {[body.location, ...(body.emails ?? []), ...(body.phones ?? [])]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
                {body.links?.length > 0 && (
                  <div className="mt-0.5 text-xs text-indigo-600">{body.links.join(" · ")}</div>
                )}
              </div>

              {body.summary && <p className="text-sm text-zinc-700">{body.summary}</p>}

              {body.roles?.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Experience</h3>
                  <div className="mt-2 space-y-4">
                    {body.roles.map((role, i) => (
                      <div key={i}>
                        <div className="text-sm font-medium text-zinc-900">
                          {role.title} — {role.company}
                          <SourceChips ids={role.source_doc_ids} builtFrom={builtFrom} />
                        </div>
                        <div className="text-xs text-zinc-400">
                          {[role.location, [role.start, role.end].filter(Boolean).join(" → ")]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                        <Bullets bullets={role.bullets} builtFrom={builtFrom} />
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {body.education?.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Education</h3>
                  <div className="mt-2 space-y-2">
                    {body.education.map((ed, i) => (
                      <div key={i} className="text-sm text-zinc-700">
                        <span className="font-medium text-zinc-900">{ed.degree}</span>
                        {ed.field ? `, ${ed.field}` : ""} — {ed.institution}
                        <span className="text-xs text-zinc-400">
                          {" "}
                          {[ed.start, ed.end].filter(Boolean).join(" → ")}
                          {ed.gpa ? ` · GPA ${ed.gpa}` : ""}
                        </span>
                        <SourceChips ids={ed.source_doc_ids} builtFrom={builtFrom} />
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {body.projects?.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Projects</h3>
                  <div className="mt-2 space-y-3">
                    {body.projects.map((project, i) => (
                      <div key={i}>
                        <div className="text-sm font-medium text-zinc-900">
                          {project.name}
                          {project.organization ? (
                            <span className="font-normal text-zinc-500"> · {project.organization}</span>
                          ) : null}
                          <SourceChips ids={project.source_doc_ids} builtFrom={builtFrom} />
                        </div>
                        {(project.dates || project.outcome) && (
                          <div className="text-xs text-zinc-400">
                            {[project.dates, project.outcome].filter(Boolean).join(" · ")}
                          </div>
                        )}
                        <Bullets bullets={project.bullets} builtFrom={builtFrom} />
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {body.publications?.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Publications</h3>
                  <Bullets bullets={body.publications} builtFrom={builtFrom} />
                </section>
              )}

              {body.skills?.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Skills</h3>
                  <div className="mt-2 space-y-1">
                    {body.skills.map((group, i) => (
                      <div key={i} className="text-sm text-zinc-700">
                        <span className="font-medium text-zinc-900">{group.name}:</span>{" "}
                        {group.items.join(", ")}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {body.voice_notes?.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
                    Cover-letter voice
                  </h3>
                  <ul className="mt-1.5 space-y-1">
                    {body.voice_notes.map((noteText, i) => (
                      <li key={i} className="text-sm italic text-zinc-500">
                        “{noteText}”
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {body.other_facts?.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Also on file</h3>
                  <Bullets bullets={body.other_facts} builtFrom={builtFrom} />
                </section>
              )}

              {body.narrative && (
                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Narrative</h3>
                  <p className="mt-1.5 whitespace-pre-line text-sm text-zinc-600">{body.narrative}</p>
                </section>
              )}

              <details
                onToggle={(e) => {
                  if ((e.target as HTMLDetailsElement).open && editJson === null) {
                    setEditJson(JSON.stringify(body, null, 2));
                  }
                }}
              >
                <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-600">
                  Edit raw profile (JSON)
                </summary>
                <textarea
                  className="mt-2 h-64 w-full rounded-md border border-zinc-300 p-2 font-mono text-xs"
                  value={editJson ?? ""}
                  onChange={(e) => setEditJson(e.target.value)}
                />
                <Button
                  className="mt-2"
                  variant="outline"
                  onClick={() =>
                    void act(async () => {
                      const parsed = JSON.parse(editJson ?? "{}");
                      await api.put(`/profiles/${pid}/profile`, { body: parsed });
                      setEditJson(null);
                    })
                  }
                >
                  Save as new version
                </Button>
              </details>
            </div>
          )}
        </CardBody>
      </Card>

      {/* 3 — interview */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>3 · Gap interview</CardTitle>
          {answeredQs.length > 0 && (
            <Button
              onClick={() => void act(() => api.post(`/profiles/${pid}/refine`))}
              disabled={llmBusy}
            >
              {llmBusy ? <Spinner /> : <CheckCircle2 className="h-4 w-4" />}
              Apply {answeredQs.length} answer{answeredQs.length > 1 ? "s" : ""} to profile
            </Button>
          )}
        </CardHeader>
        <CardBody className="space-y-4">
          {openQs.length === 0 && answeredQs.length === 0 && (
            <p className="text-sm text-zinc-400">
              {mp
                ? "No open questions — the profile has no known gaps."
                : "Questions appear here after the first build."}
            </p>
          )}

          {openQs.map((q) => (
            <OpenQuestionRow
              key={q.id}
              q={q}
              onAnswer={(text) =>
                void act(() => api.post(`/profiles/${pid}/questions/${q.id}/answer`, { answer: text }))
              }
              onSkip={() => void act(() => api.post(`/profiles/${pid}/questions/${q.id}/skip`))}
            />
          ))}

          {answeredQs.length > 0 && (
            <div className="rounded-md bg-amber-50/60 px-3 py-2 text-xs text-amber-700">
              {answeredQs.length} answer{answeredQs.length > 1 ? "s" : ""} waiting — click “Apply …
              to profile” above to fold them in.
            </div>
          )}

          {(answeredQs.length > 0 || appliedQs.length > 0) && (
            <details>
              <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-600">
                Answered ({answeredQs.length + appliedQs.length})
              </summary>
              <ul className="mt-2 space-y-2">
                {[...answeredQs, ...appliedQs].map((q) => (
                  <li key={q.id} className="text-sm">
                    <div className="text-zinc-500">{q.question}</div>
                    <div className="text-zinc-800">→ {q.answer}</div>
                    {q.status === "applied" && <Badge tone="green">applied</Badge>}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <form
            className="flex gap-2 border-t border-zinc-100 pt-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!note.trim()) return;
              void act(async () => {
                await api.post(`/profiles/${pid}/notes`, { text: note.trim() });
                setNote("");
              });
            }}
          >
            <Input
              placeholder="Anything else the agent should know? (added on next apply)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <Button type="submit" variant="outline" disabled={!note.trim()} className="shrink-0">
              <Send className="h-4 w-4" /> Add
            </Button>
          </form>
        </CardBody>
      </Card>

      {/* 4 — target job preferences */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>4 · What you're looking for</CardTitle>
          {prefs && (
            <span className="text-xs text-zinc-400">
              v{prefs.version} · parsed {new Date(prefs.created_at).toLocaleString()}
            </span>
          )}
        </CardHeader>
        <CardBody className="space-y-4">
          <p className="text-sm text-zinc-500">
            Describe the job you want in your own words — roles, places, remote stance, salary
            expectations, industries, dealbreakers, anything. The agent turns it into the search
            profile used for discovery and scoring.
          </p>
          <textarea
            className="h-32 w-full rounded-md border border-zinc-300 p-3 text-sm placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            placeholder='e.g. "Senior ML engineer or applied scientist, Toronto or remote in Canada, 140k+ CAD, no crypto, prefer research-flavored teams…"'
            value={prefsText}
            onChange={(e) => setPrefsText(e.target.value)}
          />
          <Button
            disabled={prefsText.trim().length < 10 || prefsBusy}
            onClick={() =>
              void (async () => {
                setPrefsBusy(true);
                await act(() =>
                  api.post(`/profiles/${pid}/preferences/parse`, { raw_text: prefsText.trim() }),
                );
                setPrefsBusy(false);
                setPrefsJson(null);
              })()
            }
          >
            {prefsBusy ? <Spinner /> : <Sparkles className="h-4 w-4" />}
            {prefs ? "Re-parse description" : "Parse with the agent"}
          </Button>

          {prefs && (
            <div className="space-y-2.5 border-t border-zinc-100 pt-4">
              <PrefRow label="Titles">
                <Chips items={prefs.structured.target_titles} tone="indigo" />
              </PrefRow>
              <PrefRow label="Seniority">{prefs.structured.seniority ?? "—"}</PrefRow>
              <PrefRow label="Locations">
                <Chips items={prefs.structured.locations} />
              </PrefRow>
              <PrefRow label="Remote">{prefs.structured.remote_stance ?? "—"}</PrefRow>
              <PrefRow label="Job types">
                <Chips items={prefs.structured.job_types} />
              </PrefRow>
              <PrefRow label="Salary">
                {prefs.structured.salary
                  ? `${prefs.structured.salary.floor?.toLocaleString() ?? "?"} – ${
                      prefs.structured.salary.target?.toLocaleString() ?? "?"
                    } ${prefs.structured.salary.currency ?? ""}${
                      prefs.structured.salary.notes ? ` (${prefs.structured.salary.notes})` : ""
                    }`
                  : "—"}
              </PrefRow>
              <PrefRow label="Watchlist">
                <Chips items={prefs.structured.company_watchlist} tone="green" />
              </PrefRow>
              <PrefRow label="Avoid">
                <Chips
                  items={[
                    ...prefs.structured.industries_avoid,
                    ...prefs.structured.company_blocklist,
                  ]}
                  tone="red"
                />
              </PrefRow>
              <PrefRow label="Dealbreakers">
                <Chips items={prefs.structured.dealbreakers} tone="red" />
              </PrefRow>
              <PrefRow label="Nice to have">
                <Chips items={prefs.structured.soft_preferences} tone="green" />
              </PrefRow>
              <PrefRow label="Keywords">
                <span className="flex flex-wrap items-center gap-1">
                  <Chips items={prefs.structured.keywords_must} tone="indigo" />
                  {prefs.structured.keywords_exclude.length > 0 && (
                    <>
                      <span className="text-xs text-zinc-400">exclude:</span>
                      <Chips items={prefs.structured.keywords_exclude} tone="red" />
                    </>
                  )}
                </span>
              </PrefRow>
              <PrefRow label="Work auth">{prefs.structured.work_authorization ?? "—"}</PrefRow>
              {prefs.structured.notes.length > 0 && (
                <PrefRow label="Notes">{prefs.structured.notes.join(" · ")}</PrefRow>
              )}

              {prefs.structured.clarifications_needed.length > 0 && (
                <div className="rounded-md bg-amber-50/70 px-3 py-2">
                  <div className="text-xs font-medium text-amber-800">
                    The agent wants to confirm:
                  </div>
                  <ul className="mt-1 list-disc pl-4 text-sm text-amber-800">
                    {prefs.structured.clarifications_needed.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                  <div className="mt-1 text-xs text-amber-700">
                    Refine your description above and re-parse, or edit the JSON below.
                  </div>
                </div>
              )}

              <details
                onToggle={(e) => {
                  if ((e.target as HTMLDetailsElement).open && prefsJson === null) {
                    setPrefsJson(JSON.stringify(prefs.structured, null, 2));
                  }
                }}
              >
                <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-600">
                  Edit raw preferences (JSON)
                </summary>
                <textarea
                  className="mt-2 h-48 w-full rounded-md border border-zinc-300 p-2 font-mono text-xs"
                  value={prefsJson ?? ""}
                  onChange={(e) => setPrefsJson(e.target.value)}
                />
                <Button
                  className="mt-2"
                  variant="outline"
                  onClick={() =>
                    void act(async () => {
                      const parsed = JSON.parse(prefsJson ?? "{}");
                      await api.put(`/profiles/${pid}/preferences`, { structured: parsed });
                      setPrefsJson(null);
                    })
                  }
                >
                  Save as new version
                </Button>
              </details>
            </div>
          )}
        </CardBody>
      </Card>

      {/* 5 — résumé design */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>5 · Résumé design</CardTitle>
          {design.trim() && <Badge tone="green">custom</Badge>}
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm text-zinc-500">
            Shape how your résumé is written — bullet style, tone, what to emphasize or leave off
            (e.g. “leave off my bachelor”). Set the length with the buttons; the app enforces it by
            tightening the layout, and only re-asks the AI to trim if it truly can’t fit. The agent
            never fabricates anything.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-zinc-400">Target length</span>
            {[
              { v: 1, l: "1 page" },
              { v: 2, l: "2 pages" },
              { v: 0, l: "No limit" },
            ].map((o) => (
              <Button
                key={o.v}
                variant={pages === o.v ? "primary" : "outline"}
                onClick={() => setPages(o.v)}
              >
                {o.l}
              </Button>
            ))}
          </div>
          <textarea
            className="h-40 w-full rounded-md border border-zinc-300 p-3 text-sm placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            placeholder={
              "e.g.\n• Keep it to a single page.\n• Two full pages is fine — use the space.\n• Every bullet must fit on one line; no wrapping.\n• Lead each bullet with a metric.\n• At most 3 bullets per role."
            }
            maxLength={2000}
            value={design}
            onChange={(e) => setDesign(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <Button onClick={() => void saveDesign()}>
              <Save className="h-4 w-4" /> Save
            </Button>
            {designMsg && <span className="text-sm text-emerald-600">{designMsg}</span>}
            <span className="ml-auto text-xs text-zinc-400">{design.length}/2000</span>
          </div>
        </CardBody>
      </Card>

      {/* 6 — discovery */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>6 · Discovery</CardTitle>
          <div className="flex items-center gap-2">
            <Link
              to={`/profiles/${pid}/jobs`}
              className="inline-flex items-center gap-1 text-sm text-indigo-600 hover:underline"
            >
              View jobs <ArrowRight className="h-3.5 w-3.5" />
            </Link>
            <Button
              disabled={!prefs || runBusy}
              onClick={() => void act(() => api.post(`/profiles/${pid}/runs`, { kind: "full" }))}
            >
              {runBusy ? <Spinner /> : <Radar className="h-4 w-4" />}
              {runBusy ? "Hunting…" : "Run pipeline"}
            </Button>
          </div>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-end gap-4 border-b border-zinc-100 pb-3">
            <ModelSelect
              label="scoring model"
              value={modelScore}
              onChange={(v) => {
                setModelScore(v);
                void persistModels(v, modelTailor);
              }}
            />
            <ModelSelect
              label="tailoring model"
              value={modelTailor}
              onChange={(v) => {
                setModelTailor(v);
                void persistModels(modelScore, v);
              }}
            />
            <p className="max-w-xs text-xs text-zinc-400">
              Models used when you run the pipeline (scoring on every job, tailoring on
              shortlisted). Saved instantly; also editable in the schedule card below.
            </p>
          </div>
          {!prefs && (
            <p className="text-sm text-zinc-400">
              Set your preferences (card 4) first — discovery executes them.
            </p>
          )}
          {prefs && !latestRun && (
            <p className="text-sm text-zinc-400">
              Never run yet. Sources come from Settings: JSearch + Adzuna (+ Jooble), plus the
              public job boards of any companies in your watchlist.
            </p>
          )}
          {latestRun && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-600">
                <Badge
                  tone={
                    latestRun.status === "done"
                      ? "green"
                      : latestRun.status === "failed"
                        ? "red"
                        : "indigo"
                  }
                >
                  {latestRun.status}
                </Badge>
                <span className="text-xs text-zinc-400">
                  {new Date(latestRun.started_at).toLocaleString()}
                </span>
                {latestRun.status !== "running" && runDisc && (
                  <span>
                    {runDisc.new ?? 0} new · {runDisc.merged_duplicates ?? 0} duplicates merged ·{" "}
                    {runDisc.irrelevant_skipped ?? 0} off-target skipped
                  </span>
                )}
              </div>
              {latestRun.status !== "running" && runScor && (
                <div className="text-sm text-zinc-600">
                  Scored {runScor.scored ?? 0} · shortlisted{" "}
                  <span className="font-medium text-emerald-700">{runScor.shortlisted ?? 0}</span>
                  {runScor.avg_score != null && <> · avg fit {runScor.avg_score}</>}
                  {runScor.failed ? <> · {runScor.failed} failed</> : null}
                </div>
              )}
              {latestRun.status !== "running" && runTail && (
                <div className="text-sm text-zinc-600">
                  Tailored {runTail.tailored ?? 0} packet(s) · {runTail.cover_letters ?? 0} cover
                  letter(s)
                  {runTail.audit_flagged ? <> · {runTail.audit_flagged} audit-flagged</> : null}
                  {runTail.failed ? <> · {runTail.failed} failed</> : null}
                </div>
              )}
              {runDisc?.by_source && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(runDisc.by_source).map(([source, count]) => (
                    <Badge key={source} tone="zinc">
                      {source}: {count}
                    </Badge>
                  ))}
                </div>
              )}
              {latestRun.errors.length > 0 && (
                <ul className="rounded-md bg-amber-50/70 px-3 py-2 text-xs text-amber-800">
                  {latestRun.errors.map((err) => (
                    <li key={err.source}>
                      <span className="font-medium">{err.source}:</span> {err.error}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {/* 7 — telegram delivery */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>7 · Telegram delivery</CardTitle>
          {tg?.connected && <Badge tone="green">connected ✓</Badge>}
          {tgPending && <Badge tone="amber">waiting for /start</Badge>}
        </CardHeader>
        <CardBody className="space-y-3">
          {!tg?.status && (
            <>
              <p className="text-sm text-zinc-500">
                Get every packet on your phone — with Applied / Skip / Re-tailor buttons and a{" "}
                <code>/run</code> command. Two minutes, all self-service:
              </p>
              <ol className="list-decimal space-y-1 pl-5 text-sm text-zinc-600">
                <li>
                  In Telegram, open <span className="font-medium">@BotFather</span> → send{" "}
                  <code>/newbot</code> → pick any name → copy the token it gives you.
                </li>
                <li>Paste the token here and connect.</li>
              </ol>
              <form
                className="flex max-w-xl gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (tgToken.trim().length < 20 || tgBusy) return;
                  void (async () => {
                    setTgBusy(true);
                    setTgMsg(null);
                    try {
                      await api.post(`/profiles/${pid}/telegram`, { token: tgToken.trim() });
                      setTgToken("");
                      await refresh();
                    } catch (err) {
                      setTgMsg({ ok: false, text: (err as Error).message });
                    } finally {
                      setTgBusy(false);
                    }
                  })();
                }}
              >
                <Input
                  type="password"
                  placeholder="Paste the bot token from @BotFather"
                  value={tgToken}
                  onChange={(e) => setTgToken(e.target.value)}
                  autoComplete="off"
                />
                <Button type="submit" disabled={tgToken.trim().length < 20 || tgBusy} className="shrink-0">
                  {tgBusy ? <Spinner /> : <Send className="h-4 w-4" />} Connect
                </Button>
              </form>
            </>
          )}

          {tgPending && tg?.link_url && (
            <div className="space-y-2">
              <p className="text-sm text-zinc-600">
                Bot <span className="font-medium">@{tg.bot_username}</span> registered. Last step —
                open it and press START:
              </p>
              <a href={tg.link_url} target="_blank" rel="noreferrer">
                <Button>
                  <Send className="h-4 w-4" /> Open @{tg.bot_username} in Telegram
                </Button>
              </a>
              <p className="flex items-center gap-2 text-xs text-zinc-400">
                <Spinner className="h-3 w-3" /> waiting for your /start — this card updates by
                itself
              </p>
              <Button
                variant="ghost"
                onClick={() => void act(async () => {
                  await api.del(`/profiles/${pid}/telegram`);
                  setTgMsg(null);
                })}
              >
                Cancel
              </Button>
            </div>
          )}

          {tg?.connected && (
            <div className="space-y-2">
              <p className="text-sm text-zinc-600">
                Packets deliver to <span className="font-medium">@{tg.bot_username}</span>{" "}
                automatically after every run — and <code>/run</code> from your phone starts the
                pipeline.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() =>
                    void (async () => {
                      setTgMsg(null);
                      try {
                        await api.post(`/profiles/${pid}/telegram/test`);
                        setTgMsg({ ok: true, text: "Test message sent — check Telegram." });
                      } catch (err) {
                        setTgMsg({ ok: false, text: (err as Error).message });
                      }
                    })()
                  }
                >
                  Send test message
                </Button>
                <Button
                  variant="danger"
                  onClick={() => {
                    if (!window.confirm("Disconnect Telegram for this profile?")) return;
                    void act(() => api.del(`/profiles/${pid}/telegram`));
                  }}
                >
                  Disconnect
                </Button>
              </div>
            </div>
          )}

          {tgMsg && (
            <p className={`text-sm ${tgMsg.ok ? "text-emerald-600" : "text-red-600"}`}>
              {tgMsg.text}
            </p>
          )}
        </CardBody>
      </Card>

      {/* 8 — schedule & limits */}
      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>8 · Schedule & limits</CardTitle>
          {schedEnabled ? (
            <Badge tone="green">daily at {schedTime}</Badge>
          ) : (
            <Badge tone="zinc">manual only</Badge>
          )}
        </CardHeader>
        <CardBody className="space-y-4">
          <p className="text-sm text-zinc-500">
            The full pipeline (discover → score → tailor) runs automatically once a day while the
            app is running. If the laptop was asleep at the target time, it catches up on wake.
          </p>
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                className="h-4 w-4 accent-indigo-600"
                checked={schedEnabled}
                onChange={(e) => setSchedEnabled(e.target.checked)}
              />
              Run every morning
            </label>
            <label className="text-sm text-zinc-700">
              <span className="mb-1 block text-xs text-zinc-400">at</span>
              <Input
                type="time"
                className="w-32"
                value={schedTime}
                onChange={(e) => setSchedTime(e.target.value)}
              />
            </label>
            <label className="text-sm text-zinc-700">
              <span className="mb-1 block text-xs text-zinc-400">score cap / run</span>
              <Input
                type="number"
                className="w-24"
                min={1}
                max={200}
                value={capScore}
                onChange={(e) => setCapScore(Number(e.target.value) || 80)}
              />
            </label>
            <label className="text-sm text-zinc-700">
              <span className="mb-1 block text-xs text-zinc-400">tailor cap / run</span>
              <Input
                type="number"
                className="w-24"
                min={0}
                max={25}
                value={capTailor}
                onChange={(e) => setCapTailor(Number(e.target.value) || 5)}
              />
            </label>
            <ModelSelect label="scoring model" value={modelScore} onChange={setModelScore} />
            <ModelSelect label="tailoring model" value={modelTailor} onChange={setModelTailor} />
            <Button onClick={() => void saveSchedule()}>
              <AlarmClock className="h-4 w-4" /> Save
            </Button>
          </div>
          {schedMsg && <p className="text-sm text-emerald-600">{schedMsg}</p>}
          <p className="text-xs text-zinc-400">
            Caps bound the LLM spend per run; the models set the cost/quality tradeoff (Haiku
            cheapest, Opus best). Scoring runs on every discovered job, so a cheaper model there
            saves the most; tailoring writes your résumé + cover letter, where quality matters more.
            To run unattended without keeping a terminal open, install the launchd service — see
            “Run as a background service” in the README.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

function PrefRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] items-baseline gap-2 text-sm">
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-400">{label}</span>
      <span className="text-zinc-700">{children}</span>
    </div>
  );
}

function Chips({
  items,
  tone = "zinc",
}: {
  items: string[];
  tone?: "zinc" | "red" | "green" | "indigo" | "amber";
}) {
  if (!items || items.length === 0) return <span className="text-zinc-300">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((item) => (
        <Badge key={item} tone={tone}>
          {item}
        </Badge>
      ))}
    </span>
  );
}

function OpenQuestionRow({
  q,
  onAnswer,
  onSkip,
}: {
  q: QuestionItem;
  onAnswer: (text: string) => void;
  onSkip: () => void;
}) {
  const [text, setText] = useState("");
  return (
    <div className="rounded-lg border border-zinc-200 p-3">
      <div className="flex items-start gap-2">
        <MessageCircleQuestion className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
        <div className="flex-1">
          <div className="text-sm font-medium text-zinc-900">{q.question}</div>
          {q.reason && <div className="mt-0.5 text-xs text-zinc-400">{q.reason}</div>}
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) onAnswer(text.trim());
            }}
          >
            <Input
              placeholder="Your answer…"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <Button type="submit" disabled={!text.trim()} className="shrink-0">
              Answer
            </Button>
            <Button type="button" variant="ghost" onClick={onSkip} className="shrink-0" title="Skip">
              <XCircle className="h-4 w-4" />
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
