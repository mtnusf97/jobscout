import { ExternalLink, KeyRound, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Input, Spinner } from "../components/ui";
import { api, type CredentialResult, type CredentialState } from "../lib/api";

function StatusBadge({ state }: { state: CredentialState }) {
  if (!state.is_set) return <Badge tone="zinc">Not set</Badge>;
  if (state.validation === "live") {
    return state.last_validated_at ? (
      <Badge tone="green">Validated ✓</Badge>
    ) : (
      <Badge tone="amber">Saved — not validated</Badge>
    );
  }
  return <Badge tone="indigo">Saved</Badge>;
}

function CredentialRow({
  state,
  onChanged,
}: {
  state: CredentialState;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(!state.is_set);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    setEditing(!state.is_set);
  }, [state.is_set]);

  async function save() {
    if (!value.trim() || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const res = await api.put<CredentialResult>(`/credentials/${state.name}`, {
        value: value.trim(),
      });
      setResult({ ok: res.valid, text: res.message });
      setValue("");
      onChanged();
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function revalidate() {
    setBusy(true);
    setResult(null);
    try {
      const res = await api.post<CredentialResult>(`/credentials/${state.name}/validate`);
      setResult({ ok: res.valid, text: res.message });
      onChanged();
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Remove the stored ${state.label}?`)) return;
    try {
      await api.del(`/credentials/${state.name}`);
      setResult(null);
      onChanged();
    } catch (e) {
      setResult({ ok: false, text: (e as Error).message });
    }
  }

  return (
    <div className="py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-900">{state.label}</span>
            <StatusBadge state={state} />
          </div>
          <p className="mt-1 max-w-xl text-sm text-zinc-500">{state.description}</p>
          <a
            href={state.help_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"
          >
            Get this key <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      </div>

      <div className="mt-3">
        {editing ? (
          <form
            className="flex max-w-xl flex-wrap gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <Input
              type="password"
              placeholder={`Paste your ${state.label} here`}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoComplete="off"
              aria-label={state.label}
            />
            <Button type="submit" disabled={busy || !value.trim()} className="shrink-0">
              {busy ? <Spinner /> : <KeyRound className="h-4 w-4" />}
              {state.validation === "live" ? "Save & validate" : "Save"}
            </Button>
            {state.is_set && (
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            )}
          </form>
        ) : (
          <div className="flex max-w-xl flex-wrap items-center gap-2">
            <code className="rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-600">
              {state.masked_value}
            </code>
            {state.last_validated_at && (
              <span className="text-xs text-zinc-400">
                validated {new Date(state.last_validated_at).toLocaleString()}
              </span>
            )}
            <span className="flex-1" />
            <Button variant="outline" onClick={() => setEditing(true)}>
              Replace
            </Button>
            {state.validation === "live" && (
              <Button variant="ghost" disabled={busy} onClick={() => void revalidate()}>
                {busy ? <Spinner /> : "Re-validate"}
              </Button>
            )}
            <Button variant="danger" onClick={() => void remove()}>
              Remove
            </Button>
          </div>
        )}
        {result && (
          <p className={`mt-2 text-sm ${result.ok ? "text-emerald-600" : "text-red-600"}`}>
            {result.text}
          </p>
        )}
      </div>
    </div>
  );
}

export default function Settings() {
  const [creds, setCreds] = useState<CredentialState[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .get<CredentialState[]>("/credentials")
      .then(setCreds)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(refresh, [refresh]);

  if (error) {
    return (
      <Card className="border-red-200">
        <CardBody className="text-sm text-red-700">Failed to load settings: {error}</CardBody>
      </Card>
    );
  }
  if (!creds) {
    return (
      <div className="flex justify-center py-24 text-zinc-400">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const neededNow = creds.filter((c) => c.phase <= 0);
  const neededLater = creds.filter((c) => c.phase > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Everything is set up here in the UI — no config files. Keys are encrypted at rest and
          shown masked once saved.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Needed now</CardTitle>
        </CardHeader>
        <CardBody className="divide-y divide-zinc-100 py-1">
          {neededNow.map((c) => (
            <CredentialRow key={c.name} state={c} onChanged={refresh} />
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Needed later — Phase 3 (job discovery)</CardTitle>
        </CardHeader>
        <CardBody className="divide-y divide-zinc-100 py-1">
          {neededLater.map((c) => (
            <CredentialRow key={c.name} state={c} onChanged={refresh} />
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Telegram</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="flex items-center gap-3 text-sm text-zinc-500">
            <Send className="h-4 w-4 shrink-0 text-zinc-400" />
            <p>
              Telegram is connected per profile — open your profile page and use card{" "}
              <span className="font-medium">6 · Telegram delivery</span> (create a bot with
              @BotFather, paste the token, press START — done).
            </p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
