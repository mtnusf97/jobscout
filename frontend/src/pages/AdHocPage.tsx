import { ArrowLeft, ClipboardPaste } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Spinner } from "../components/ui";
import { api } from "../lib/api";

export default function AdHocPage() {
  const params = useParams<{ id: string }>();
  const pid = params.id ?? "";
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (text.trim().length < 50 || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/profiles/${pid}/adhoc`, {
        text: text.trim(),
        url: url.trim() || null,
      });
      navigate(`/profiles/${pid}/jobs`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          to={`/profiles/${pid}/jobs`}
          className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
        >
          <ArrowLeft className="h-3 w-3" /> review queue
        </Link>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">Paste a job</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Found a posting yourself? Paste the description — the agent scores it and builds a
          tailored packet immediately.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Job description</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <textarea
            className="h-64 w-full rounded-md border border-zinc-300 p-3 text-sm placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            placeholder="Paste the full job description here…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Input
            placeholder="Application link (optional)"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button disabled={text.trim().length < 50 || busy} onClick={() => void submit()}>
            {busy ? <Spinner /> : <ClipboardPaste className="h-4 w-4" />}
            {busy ? "Reading the posting…" : "Score & tailor it"}
          </Button>
          <p className="text-xs text-zinc-400">
            Takes a few minutes — you'll land on the review queue where it shows up as
            “tailoring…”.
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
