import { ChevronRight, Pencil, Trash2, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Spinner } from "../components/ui";
import { api, type Profile } from "../lib/api";

export default function Profiles() {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .get<Profile[]>("/profiles")
      .then(setProfiles)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(refresh, [refresh]);

  async function create() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.post<Profile>("/profiles", { name: name.trim() });
      setName("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function rename(profile: Profile) {
    const next = window.prompt("New name for this profile:", profile.name);
    if (!next || !next.trim() || next.trim() === profile.name) return;
    try {
      await api.patch<Profile>(`/profiles/${profile.id}`, { name: next.trim() });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(profile: Profile) {
    if (!window.confirm(`Delete profile "${profile.name}"? All of its data goes with it.`)) return;
    try {
      await api.del(`/profiles/${profile.id}`);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Profiles</h1>
        <p className="mt-1 text-sm text-zinc-500">
          One profile per person. Documents, preferences, and the job pipeline all hang off a
          profile — onboarding arrives in Phase 1.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>New profile</CardTitle>
        </CardHeader>
        <CardBody>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void create();
            }}
          >
            <Input
              placeholder="Name, e.g. Matin"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-label="Profile name"
            />
            <Button type="submit" disabled={busy || !name.trim()} className="shrink-0">
              {busy ? <Spinner /> : <UserPlus className="h-4 w-4" />} Create
            </Button>
          </form>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Existing</CardTitle>
        </CardHeader>
        <CardBody>
          {profiles === null ? (
            <div className="flex justify-center py-8 text-zinc-400">
              <Spinner className="h-5 w-5" />
            </div>
          ) : profiles.length === 0 ? (
            <p className="py-4 text-sm text-zinc-400">No profiles yet — create the first one above.</p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {profiles.map((profile) => (
                <li key={profile.id} className="flex items-center justify-between py-3">
                  <Link to={`/profiles/${profile.id}`} className="group flex-1">
                    <div className="flex items-center gap-1 text-sm font-medium text-zinc-900 group-hover:text-indigo-700">
                      {profile.name}
                      <ChevronRight className="h-3.5 w-3.5 text-zinc-300 group-hover:text-indigo-400" />
                    </div>
                    <div className="text-xs text-zinc-400">
                      created {new Date(profile.created_at).toLocaleDateString()} · open onboarding
                    </div>
                  </Link>
                  <div className="flex gap-1">
                    <Button variant="ghost" onClick={() => void rename(profile)} title="Rename">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="danger" onClick={() => void remove(profile)} title="Delete">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
