const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      body && typeof body.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(res.status, detail);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: data === undefined ? undefined : JSON.stringify(data),
    }),
  put: <T>(path: string, data: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(data) }),
  patch: <T>(path: string, data: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(data) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: async <T>(path: string, files: File[]): Promise<T> => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const detail =
        body && typeof body.detail === "string" ? body.detail : res.statusText;
      throw new ApiError(res.status, detail);
    }
    return body as T;
  },
};

export interface Health {
  status: string;
  app: string;
  version: string;
}

export interface Profile {
  id: string;
  name: string;
  created_at: string;
  settings: Record<string, unknown>;
}

export interface CredentialState {
  name: string;
  label: string;
  description: string;
  help_url: string;
  phase: number;
  validation: "live" | "format";
  is_set: boolean;
  masked_value: string | null;
  last_validated_at: string | null;
}

export interface CredentialResult {
  state: CredentialState;
  valid: boolean;
  message: string;
}

export interface DocumentItem {
  id: string;
  filename: string;
  mime: string;
  size_bytes: number;
  status: "uploaded" | "processing" | "extracted" | "failed";
  error: string | null;
  doc_type: string | null;
  uploaded_at: string;
  processed_at: string | null;
}

export interface OnboardingStatus {
  status: string;
  error?: string | null;
}

export interface BuiltFromEntry {
  doc_id: string;
  filename: string;
}

export interface PBullet {
  text: string;
  source_doc_ids: string[];
}

export interface PRole {
  company: string;
  title: string;
  location?: string | null;
  start?: string | null;
  end?: string | null;
  bullets: PBullet[];
  source_doc_ids: string[];
}

export interface PEducation {
  institution: string;
  degree: string;
  field?: string | null;
  start?: string | null;
  end?: string | null;
  gpa?: string | null;
  notes: string[];
  source_doc_ids: string[];
}

export interface PProject {
  name: string;
  organization?: string | null;
  dates?: string | null;
  bullets: PBullet[];
  outcome?: string | null;
  source_doc_ids: string[];
}

export interface PSkillGroup {
  name: string;
  items: string[];
}

export interface MasterBody {
  full_name?: string | null;
  headline?: string | null;
  location?: string | null;
  emails: string[];
  phones: string[];
  links: string[];
  summary?: string | null;
  roles: PRole[];
  education: PEducation[];
  projects: PProject[];
  publications: PBullet[];
  skills: PSkillGroup[];
  certifications: string[];
  awards: string[];
  languages: string[];
  voice_notes: string[];
  other_facts: PBullet[];
  narrative?: string | null;
}

export interface MasterProfileOut {
  version: number;
  origin: string;
  created_at: string;
  built_from: Record<string, BuiltFromEntry>;
  body: MasterBody;
}

export interface QuestionItem {
  id: string;
  question: string;
  reason: string | null;
  status: "open" | "answered" | "applied" | "skipped";
  answer: string | null;
  created_at: string;
}

export interface SalaryPref {
  floor?: number | null;
  target?: number | null;
  currency?: string | null;
  notes?: string | null;
}

export interface JobPreferences {
  target_titles: string[];
  seniority?: string | null;
  locations: string[];
  remote_stance?: string | null;
  job_types: string[];
  salary?: SalaryPref | null;
  industries_preferred: string[];
  industries_avoid: string[];
  company_watchlist: string[];
  company_blocklist: string[];
  work_authorization?: string | null;
  dealbreakers: string[];
  soft_preferences: string[];
  keywords_must: string[];
  keywords_exclude: string[];
  notes: string[];
  clarifications_needed: string[];
}

export interface PreferencesOut {
  version: number;
  raw_text: string;
  structured: JobPreferences;
  created_at: string;
}

export interface DiscoveryStats {
  total_fetched?: number;
  new?: number;
  merged_duplicates?: number;
  irrelevant_skipped?: number;
  by_source?: Record<string, number>;
  watchlist_size?: number;
}

export interface ScoringStats {
  scored?: number;
  shortlisted?: number;
  failed?: number;
  avg_score?: number | null;
  note?: string;
}

export interface TailoringStats {
  tailored?: number;
  cover_letters?: number;
  audit_flagged?: number;
  failed?: number;
  note?: string;
}

export interface RunOut {
  id: string;
  kind: string;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  // nested per-stage for pipeline runs; flat for legacy runs
  stats: {
    discovery?: DiscoveryStats;
    scoring?: ScoringStats;
    tailoring?: TailoringStats;
  } & DiscoveryStats;
  errors: Array<{ source: string; error: string }>;
}

export interface JobItem {
  id: string;
  company: string;
  title: string;
  location: string | null;
  remote_type: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  posted_at: string | null;
  first_seen_at: string;
  sources: string[];
  url: string;
  status: string;
  score: number | null;
  recommend: "apply" | "maybe" | "skip" | null;
  rationale: string | null;
  salary_assessment: string | null;
  salary_estimate_min: number | null;
  salary_estimate_max: number | null;
  salary_estimate_currency: string | null;
  dealbreakers: string[];
  matched: string[];
  missing: string[];
  packet: PacketBrief | null;
}

export interface PacketBrief {
  status: string;
  version: number;
  has_letter: boolean;
  audit_passed: boolean | null;
  audit_flags: number;
}

export interface TelegramState {
  connected: boolean;
  status: "pending" | "linked" | null;
  bot_username: string | null;
  link_url: string | null;
  linked_at: string | null;
}

export interface PacketOut {
  id: string;
  version: number;
  status: string;
  created_at: string;
  audit_passed: boolean | null;
  audit_summary: string | null;
  audit_findings: Array<{ claim: string; verdict: string; note: string }>;
  has_letter: boolean;
  cover_letter_hook: string | null;
  tailoring_notes: string[];
  ats_missing: string[];
  error: string | null;
}

export interface JobsList {
  count: number;
  items: JobItem[];
}
