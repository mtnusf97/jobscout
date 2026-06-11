import {
  ArrowLeft,
  Check,
  ClipboardPaste,
  ExternalLink,
  FileText,
  RefreshCw,
  Scissors,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Badge, Button, Card, CardBody, Spinner, cn } from "../components/ui";
import { api, type JobItem, type JobsList, type Profile } from "../lib/api";

function salaryText(job: JobItem): { text: string; estimated: boolean } | null {
  const fmt = (n: number) => `${Math.round(n / 1000)}k`;
  if (job.salary_min || job.salary_max) {
    const range = [job.salary_min, job.salary_max]
      .filter((n): n is number => !!n)
      .map(fmt)
      .join("–");
    return { text: `${range} ${job.salary_currency ?? ""}`.trim(), estimated: false };
  }
  if (job.salary_estimate_min || job.salary_estimate_max) {
    const range = [job.salary_estimate_min, job.salary_estimate_max]
      .filter((n): n is number => !!n)
      .map(fmt)
      .join("–");
    return {
      text: `~${range} ${job.salary_estimate_currency ?? ""} (est.)`.trim(),
      estimated: true,
    };
  }
  return null;
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <Badge tone="zinc">unscored</Badge>;
  const tone = score >= 80 ? "green" : score >= 60 ? "indigo" : score >= 40 ? "amber" : "red";
  return (
    <span
      className={cn(
        "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold",
        tone === "green" && "bg-emerald-100 text-emerald-700",
        tone === "indigo" && "bg-indigo-100 text-indigo-700",
        tone === "amber" && "bg-amber-100 text-amber-700",
        tone === "red" && "bg-red-100 text-red-600",
      )}
    >
      {score}
    </span>
  );
}

function RecommendChip({ value }: { value: JobItem["recommend"] }) {
  if (!value) return null;
  const tone = value === "apply" ? "green" : value === "maybe" ? "amber" : "zinc";
  return <Badge tone={tone}>{value}</Badge>;
}

export default function JobsPage() {
  const params = useParams<{ id: string }>();
  const pid = params.id ?? "";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [jobs, setJobs] = useState<JobsList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sort, setSort] = useState<"score" | "new">("score");
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const [p, j] = await Promise.all([
        api.get<Profile>(`/profiles/${pid}`),
        api.get<JobsList>(`/profiles/${pid}/jobs?limit=200&sort=${sort}`),
      ]);
      setProfile(p);
      setJobs(j);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [pid, sort]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const tailoringActive = jobs?.items.some((j) => j.status === "tailoring") ?? false;
  useEffect(() => {
    if (!tailoringActive) return;
    const timer = setInterval(() => void refresh(), 4000);
    return () => clearInterval(timer);
  }, [tailoringActive, refresh]);

  async function act(fn: () => Promise<unknown>) {
    setActionError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  function tailor(job: JobItem) {
    const notes = job.packet
      ? window.prompt("Re-tailor notes for the agent (optional):", "") ?? undefined
      : "";
    if (notes === undefined) return; // cancelled
    void act(() => api.post(`/profiles/${pid}/jobs/${job.id}/tailor`, { notes }));
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <Link
            to={`/profiles/${pid}`}
            className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
          >
            <ArrowLeft className="h-3 w-3" /> {profile?.name ?? "profile"}
          </Link>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">
            Review queue{jobs ? ` (${jobs.count})` : ""}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Ranked by fit against your preferences. Tailored packets arrive in Phase 5.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to={`/profiles/${pid}/adhoc`}>
            <Button variant="outline">
              <ClipboardPaste className="h-4 w-4" /> Paste a job
            </Button>
          </Link>
          <Button
            variant={sort === "score" ? "primary" : "outline"}
            onClick={() => setSort("score")}
          >
            By score
          </Button>
          <Button variant={sort === "new" ? "primary" : "outline"} onClick={() => setSort("new")}>
            Newest
          </Button>
          <Button variant="outline" onClick={() => void refresh()} disabled={busy}>
            {busy ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      {(error || actionError) && (
        <Card className="border-red-200">
          <CardBody className="text-sm text-red-700">{error ?? actionError}</CardBody>
        </Card>
      )}

      <Card>
        <CardBody>
          {!jobs ? (
            <div className="flex justify-center py-16 text-zinc-400">
              <Spinner className="h-6 w-6" />
            </div>
          ) : jobs.items.length === 0 ? (
            <p className="py-8 text-center text-sm text-zinc-400">
              Nothing yet — hit “Run pipeline” on the profile page.
            </p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {jobs.items.map((job) => {
                const salary = salaryText(job);
                return (
                  <li
                    key={job.id}
                    className={cn(
                      "py-3",
                      (job.recommend === "skip" || job.status === "skipped") && "opacity-45",
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <ScoreBadge score={job.score} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <a
                            href={job.url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-900 hover:text-indigo-700"
                          >
                            <span className="truncate">{job.title}</span>
                            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-zinc-300" />
                          </a>
                          <RecommendChip value={job.recommend} />
                          {job.dealbreakers.length > 0 && (
                            <Badge tone="red">⚠ {job.dealbreakers[0]}</Badge>
                          )}
                        </div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-zinc-500">
                          <span className="font-medium text-zinc-600">{job.company}</span>
                          {job.location && <span>· {job.location}</span>}
                          {job.remote_type && <span>· {job.remote_type}</span>}
                          {salary && (
                            <span
                              className={cn(
                                "font-medium",
                                salary.estimated ? "text-zinc-500" : "text-emerald-700",
                              )}
                            >
                              · {salary.text}
                            </span>
                          )}
                          {job.posted_at && (
                            <span>· posted {new Date(job.posted_at).toLocaleDateString()}</span>
                          )}
                          <span className="flex gap-1">
                            {job.sources.map((source) => (
                              <Badge key={source} tone={source.startsWith("ats") ? "green" : "zinc"}>
                                {source}
                              </Badge>
                            ))}
                          </span>
                        </div>
                        {job.rationale && (
                          <p className="mt-1.5 text-sm leading-snug text-zinc-600">
                            {job.rationale}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {job.status === "applied" && <Badge tone="green">✓ applied</Badge>}
                          {job.status === "skipped" && <Badge tone="zinc">skipped</Badge>}
                          {job.status === "tailoring" && (
                            <Badge tone="indigo">
                              <Spinner className="h-3 w-3" /> tailoring…
                            </Badge>
                          )}
                          {job.packet && job.packet.status !== "failed" && (
                            <>
                              <a
                                href={`/api/profiles/${pid}/jobs/${job.id}/packet/resume.pdf`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <Button variant="outline">
                                  <FileText className="h-4 w-4" /> Resume PDF
                                </Button>
                              </a>
                              {job.packet.has_letter && (
                                <a
                                  href={`/api/profiles/${pid}/jobs/${job.id}/packet/letter.pdf`}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  <Button variant="outline">
                                    <FileText className="h-4 w-4" /> Cover letter
                                  </Button>
                                </a>
                              )}
                              {job.packet.audit_passed ? (
                                <Badge tone="green">audited ✓</Badge>
                              ) : (
                                <Badge tone="amber">{job.packet.audit_flags} audit flag(s)</Badge>
                              )}
                            </>
                          )}
                          {job.packet?.status === "failed" && (
                            <Badge tone="red">tailoring failed — retry</Badge>
                          )}
                          {job.score !== null &&
                            job.status !== "tailoring" &&
                            job.status !== "applied" &&
                            job.status !== "skipped" && (
                              <Button variant="ghost" onClick={() => tailor(job)}>
                                <Scissors className="h-4 w-4" />
                                {job.packet ? "Re-tailor" : "Tailor"}
                              </Button>
                            )}
                          {job.status !== "applied" && job.status !== "skipped" && (
                            <>
                              <Button
                                variant="ghost"
                                title="Mark applied"
                                onClick={() =>
                                  void act(() =>
                                    api.post(`/profiles/${pid}/jobs/${job.id}/action`, {
                                      action: "applied",
                                    }),
                                  )
                                }
                              >
                                <Check className="h-4 w-4 text-emerald-600" />
                              </Button>
                              <Button
                                variant="ghost"
                                title="Skip"
                                onClick={() =>
                                  void act(() =>
                                    api.post(`/profiles/${pid}/jobs/${job.id}/action`, {
                                      action: "skip",
                                    }),
                                  )
                                }
                              >
                                <X className="h-4 w-4 text-zinc-400" />
                              </Button>
                            </>
                          )}
                          {(job.status === "applied" || job.status === "skipped") && (
                            <Button
                              variant="ghost"
                              onClick={() =>
                                void act(() =>
                                  api.post(`/profiles/${pid}/jobs/${job.id}/action`, {
                                    action: "restore",
                                  }),
                                )
                              }
                            >
                              undo
                            </Button>
                          )}
                        </div>
                        {(job.matched.length > 0 || job.missing.length > 0) && (
                          <details className="mt-1">
                            <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-600">
                              requirements breakdown
                              {job.salary_assessment ? " · salary assessment" : ""}
                            </summary>
                            <div className="mt-1.5 space-y-1 text-xs">
                              {job.matched.length > 0 && (
                                <div className="flex flex-wrap items-center gap-1">
                                  <span className="text-emerald-700">have:</span>
                                  {job.matched.map((m) => (
                                    <Badge key={m} tone="green">
                                      {m}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                              {job.missing.length > 0 && (
                                <div className="flex flex-wrap items-center gap-1">
                                  <span className="text-amber-700">missing:</span>
                                  {job.missing.map((m) => (
                                    <Badge key={m} tone="amber">
                                      {m}
                                    </Badge>
                                  ))}
                                </div>
                              )}
                              {job.salary_assessment && (
                                <p className="text-zinc-500">{job.salary_assessment}</p>
                              )}
                            </div>
                          </details>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
