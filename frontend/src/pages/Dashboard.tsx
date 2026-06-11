import { ArrowRight, CheckCircle2, Circle, CircleDot } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, CardBody, CardHeader, CardTitle, Spinner } from "../components/ui";
import { api, type CredentialState, type Health, type Profile } from "../lib/api";

const ROADMAP: Array<{ phase: number; label: string; status: "done" | "next" | "todo" }> = [
  { phase: 0, label: "Scaffold — app, profiles, settings", status: "done" },
  { phase: 1, label: "Document onboarding (upload → profile)", status: "done" },
  { phase: 2, label: "Target-job intake (preferences)", status: "done" },
  { phase: 3, label: "Job discovery", status: "done" },
  { phase: 4, label: "Scoring & review queue", status: "done" },
  { phase: 5, label: "Tailoring & packets", status: "done" },
  { phase: 6, label: "Telegram delivery", status: "done" },
  { phase: 7, label: "Scheduler — hands-off mornings", status: "done" },
  { phase: 8, label: "Auto-apply (optional)", status: "next" },
];

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [creds, setCreds] = useState<CredentialState[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<Health>("/health"),
      api.get<Profile[]>("/profiles"),
      api.get<CredentialState[]>("/credentials"),
    ])
      .then(([h, p, c]) => {
        setHealth(h);
        setProfiles(p);
        setCreds(c);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <Card className="border-red-200">
        <CardBody className="text-sm text-red-700">
          Backend unreachable: {error}. Is <code>./dev.sh</code> running?
        </CardBody>
      </Card>
    );
  }
  if (!health || !profiles || !creds) {
    return (
      <div className="flex justify-center py-24 text-zinc-400">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const anthropic = creds.find((c) => c.name === "anthropic_api_key");
  const keysSet = creds.filter((c) => c.is_set).length;
  const todo: Array<{ text: string; to: string }> = [];
  if (anthropic && !anthropic.is_set) {
    todo.push({ text: "Add your Anthropic API key", to: "/settings" });
  }
  if (profiles.length === 0) {
    todo.push({ text: "Create your profile", to: "/profiles" });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Your job-hunt agent. Discovery, scoring, and tailoring arrive in the next phases.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardBody>
            <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">Backend</div>
            <div className="mt-2 flex items-center gap-2">
              <Badge tone="green">ok</Badge>
              <span className="text-sm text-zinc-600">v{health.version}</span>
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">Profiles</div>
            <div className="mt-2 text-2xl font-semibold">{profiles.length}</div>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">API keys</div>
            <div className="mt-2 text-2xl font-semibold">
              {keysSet}
              <span className="text-sm font-normal text-zinc-400"> / {creds.length} set</span>
            </div>
          </CardBody>
        </Card>
      </div>

      {todo.length > 0 && (
        <Card className="border-indigo-200 bg-indigo-50/40">
          <CardBody>
            <div className="text-sm font-medium text-indigo-900">Next steps</div>
            <ul className="mt-2 space-y-1.5">
              {todo.map((t) => (
                <li key={t.text}>
                  <Link
                    to={t.to}
                    className="inline-flex items-center gap-1.5 text-sm text-indigo-700 hover:underline"
                  >
                    {t.text} <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Roadmap</CardTitle>
        </CardHeader>
        <CardBody>
          <ul className="space-y-2.5">
            {ROADMAP.map((step) => (
              <li key={step.phase} className="flex items-center gap-2.5 text-sm">
                {step.status === "done" ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                ) : step.status === "next" ? (
                  <CircleDot className="h-4 w-4 shrink-0 text-indigo-500" />
                ) : (
                  <Circle className="h-4 w-4 shrink-0 text-zinc-300" />
                )}
                <span className={step.status === "todo" ? "text-zinc-400" : "text-zinc-800"}>
                  Phase {step.phase} — {step.label}
                </span>
                {step.status === "next" && <Badge tone="indigo">up next</Badge>}
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
