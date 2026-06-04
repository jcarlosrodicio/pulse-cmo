export type WritingInstructions = {
  daily_seo_fixes?: boolean;
  reddit?: { instructions?: string; subreddits?: string[]; keywords?: string[]; region?: string };
  x?: { instructions?: string };
  linkedin?: { instructions?: string };
  hn?: { instructions?: string; keywords?: string[] };
};

export type PageSpeedSummary = {
  url?: string;
  captured_at?: string;
  mobile?: PageSpeedStrategy;
  desktop?: PageSpeedStrategy;
};

export type PageSpeedStrategy = {
  scores: {
    performance: number | null;
    accessibility: number | null;
    seo: number | null;
    best_practices: number | null;
  };
  core_web_vitals?: Record<
    string,
    { display_value?: string; numeric_value?: number; score?: number } | null
  >;
  opportunities?: Array<{
    id: string;
    title: string;
    description: string;
    score: number | null;
    savings_ms: number | null;
  }>;
};

export type SeoSummary = {
  url: string;
  score: number;
  summary: {
    title: string;
    description: string;
    h1_count: number;
    img_count: number;
    missing_alts: number;
    has_sitemap: boolean;
    has_jsonld: boolean;
  };
  counts: { high: number; medium: number; low: number };
  findings: Array<{ severity: "high" | "medium" | "low"; category: string; description: string; fix: string }>;
  passed: Array<{ check: string; category: string }>;
};

export type TractionMention = {
  title: string;
  url: string;
  snippet: string;
  date: string;
  extra?: string;
  platform: string;
  platform_label: string;
};

export type TractionPlatform = {
  key: string;
  label: string;
  count: number;
  strength: "strong" | "emerging" | "thin" | "none";
  summary: string;
  mentions: TractionMention[];
};

export type TractionSummary = {
  status: "scanning" | "done" | "failed";
  error?: string;
  started_at?: string;
  scanned_at?: string;
  query_terms?: string[];
  totals?: { mentions: number; platforms: number };
  strongest?: string | null;
  sentiment?: { positive?: number; neutral?: number; negative?: number };
  insights?: string[];
  platforms?: TractionPlatform[];
};

export type GeoEngine = { engine: string; tokens: string[]; blocked: boolean };

export type GeoSummary = {
  url: string;
  score: number;
  engines: GeoEngine[];
  signals: {
    has_llms_txt: boolean;
    has_jsonld: boolean;
    has_faq_schema: boolean;
    schema_types: string[];
    heading_count: number;
    question_headings: number;
    has_meta_description: boolean;
  };
  counts: { high: number; medium: number; low: number };
  findings: Array<{ severity: "high" | "medium" | "low"; category: string; description: string; fix: string }>;
  passed: Array<{ check: string; category: string }>;
};

export type LinksSummary = {
  url: string;
  counts: { total: number; internal: number; external: number; checked: number; broken: number };
  broken: Array<{ url: string; status: number | string }>;
  external_sample: string[];
  internal_sample: string[];
};

export type UsageTotals = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  events: number;
};

export type Project = {
  id: number;
  name: string;
  url: string;
  description: string | null;
  competitors: string[];
  brand_voice: { tone?: string; vocabulary?: string; rhythm?: string; taboo?: string[] } | null;
  schedule_hour: number;
  schedule_minute: number;
  schedule_times: string[] | null;
  timezone: string;
  writing_instructions: WritingInstructions | null;
  pagespeed_summary: PageSpeedSummary | null;
  seo_summary: SeoSummary | null;
  traction_summary: TractionSummary | null;
  geo_summary: GeoSummary | null;
  links_summary: LinksSummary | null;
  brief: Brief | null;
  created_at: string;
  // computed by the server when fetched via GET /projects[/id]
  latest_run?: RunSummary | null;
  active_run_id?: number | null;
  action_counts?: Record<string, number>;
  initial_run_id?: number | null;
};

// The marketing brief — the strategic input the first dive collects from the
// founder (some fields pre-filled by recon) before the heavy run. Mirrors
// src/pulse/brief.py.
export type Brief = {
  goal?: string;
  goal_metric?: string;
  horizon_days?: number;
  icp?: string;
  not_for?: string;
  baseline?: string;
  tried?: string;
  budget?: string;
  hours_per_week?: string;
  can_produce?: string[];
  off_limits?: string;
  wedge_hypothesis?: string;
  assets?: string;
};

export type ReconResult = {
  brief: Brief;
  crawl: { title: string; description: string; pages_fetched: number; ok: boolean };
  project: Project;
};

// --- the GTM loop (bet -> this week's moves -> the call) --------------------

export type ChannelBet = {
  channel: string;
  why_this_one: string;
  why_not_runner_up?: string;
  play: { asset: string; cadence: string; targets: string; first_asset?: string };
  leading_indicator: string;
  kill_criteria: string;
  committed_at?: string;
};

export type GtmMove = {
  move: string;
  leading_indicator: string;
  why: string;
  done: boolean;
};

export type GtmReview = {
  what_moved: string;
  attribution?: string;
  the_call: string;
  call_kind: "continue" | "adjust" | "kill";
  next_focus: string;
};

export type GtmWeek = {
  id: number;
  project_id: number;
  week_num: number;
  started_at: string;
  plan: { focus: string; moves: GtmMove[] } | null;
  snapshot: Record<string, string> | null;
  review: GtmReview | null;
};

export type GtmState = {
  bet: ChannelBet | null;
  current_week: GtmWeek | null;
  weeks: GtmWeek[];
};

// The founder's weekly snapshot — the real signal the loop reads.
export type WeeklySnapshot = {
  signups?: string;
  visitors?: string;
  top_sources?: string;
  shipped?: string;
  notes?: string;
};

export type ActionType =
  | "seo_fix"
  | "tweet"
  | "hn_post"
  | "linkedin"
  | "article"
  | "hn_opportunity"
  | "reddit_opportunity"
  | "reddit_reply"
  | "market_gap"
  | "strategy";

// Channels you can target via a `targeted` run — used by the per-channel
// "+ Generate" buttons in the Actions Feed.
export type TargetKind =
  | "tweet"
  | "linkedin"
  | "hn_post"
  | "article"
  | "reddit_reply"
  | "reddit_opportunity"
  | "hn_opportunity"
  | "seo_audit"
  | "competitor_scan"
  | "market_gap"
  | "strategy";

export type ActionContext = Record<string, unknown> & {
  variants?: string[];
  chosen_variant?: number;
  severity?: string;
  hn_url?: string;
  post_url?: string;
};

export type Action = {
  id: number;
  project_id: number;
  run_id: number | null;
  action_type: ActionType;
  title: string;
  content: string;
  context: ActionContext;
  detail_md: string | null;
  status: "pending" | "shipped" | "dismissed";
  created_at: string;
  shipped_at: string | null;
};

export type RunSummary = {
  id: number;
  kind: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  total_iterations: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  cost_micros?: number;
};

export type RunDetail = RunSummary & { project_id: number; log: AgentEvent[] };

export type AgentEvent =
  | { type: "start" }
  | { type: "iteration"; n: number }
  | { type: "text"; text: string }
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; result: string }
  | { type: "done"; iterations: number; content: string }
  | { type: "error"; message: string }
  | {
      type: "_done";
      status?: string;
      prompt_tokens?: number;
      completion_tokens?: number;
      total_tokens?: number;
      cost_usd?: number;
      llm_calls?: number;
    };

export type DocumentKind =
  | "product_information"
  | "competitor_analysis"
  | "positioning"
  | "gtm_plan"
  | "brand_voice"
  | "marketing_strategy";

export type ProjectDocument = {
  id: number;
  project_id: number;
  kind: DocumentKind;
  title: string;
  content_md: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ChatSession = {
  id: number;
  project_id: number;
  title: string;
  created_at: string;
  last_activity_at: string;
  message_count?: number;
};

export type ChatMessageRow = {
  id: number;
  session_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type ChatSessionDetail = ChatSession & { messages: ChatMessageRow[] };

export type ProviderRole = "primary" | "secondary" | "vision" | "fallback";

export type ProviderConfig = {
  name: string;
  base_url: string;
  api_key: string | null;          // "•••" indicates stored-but-redacted
  api_key_env: string | null;
  model: string;
  role: ProviderRole;
  timeout: number;
  max_retries: number;
  prompt_cost_per_million: number;
  completion_cost_per_million: number;
};

export type SettingsPayload = {
  providers: ProviderConfig[];
  default_temperature: number;
  max_iterations: number;
};

// --- launch mode -----------------------------------------------------------

export type LaunchArchetypeKey =
  | "viral_artifact"
  | "dev_tool"
  | "b2b_saas"
  | "consumer"
  | "open_source"
  | "marketplace";

export type LaunchTask = { text: string; done: boolean };

export type LaunchContentKind = "tweet" | "reddit_post" | "hn_post" | "linkedin" | "article";

export type LaunchContentPiece = {
  kind: LaunchContentKind;
  brief: string;
  status: "idea" | "drafted";
  variants: string[];
  chosen_variant: number;
  action_id: number | null;
};

export type LaunchDayMetrics = {
  visits: string;
  north: string;
  loop: string;
  referrer: string;
};

export type LaunchDay = {
  title: string;
  channel: string;
  gate: boolean;
  goal?: string;
  rationale?: string;
  date?: string;
  tasks: LaunchTask[];
  content_pieces: LaunchContentPiece[];
  metrics: LaunchDayMetrics;
};

export type LaunchChannel = {
  name: string;
  type: "repeatable" | "one_shot";
  day?: number;
  why?: string;
  target?: TargetKind | null;
};

export type LaunchPlan = {
  classification: LaunchArchetypeKey;
  archetype_label: string;
  growth_engine: string;
  positioning: { tagline?: string; one_liner?: string; share_hook?: string };
  metrics: {
    north: string;
    loop: string;
    visits: string;
    north_star_desc?: string;
    loop_desc?: string;
  };
  channels: LaunchChannel[];
  days: LaunchDay[];
  decision_rules: string[];
  guardrails: string[];
};

export type LaunchClassification = {
  archetype: LaunchArchetypeKey;
  confidence: "high" | "medium" | "low";
  reasoning: string;
  secondary?: string | null;
  watch_outs?: string[];
  facts?: {
    key: string;
    label: string;
    growth_engine: string;
    north_star: string;
    loop_metric: string;
    channels: LaunchChannel[];
    avoid: string[];
  };
};

export type LaunchIntake = {
  one_liner?: string;
  pricing?: string;
  has_retention_loop?: boolean | null;
  primary_artifact?: string;
  audience_who?: string;
  founder_can_produce?: string[];
  founder_reach?: string;
  budget?: string;
  og_unfurl_works?: boolean | null;
  goal?: string;
  launch_date?: string;
};

export type LaunchCampaign = {
  id: number;
  project_id: number;
  state: "intake" | "classify" | "plan" | "active" | "done";
  archetype: LaunchArchetypeKey | null;
  classification: LaunchClassification | null;
  intake: LaunchIntake;
  plan: LaunchPlan | null;
  start_date: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectVersion = {
  id: number;
  project_id: number;
  version_num: number;
  run_id: number | null;
  kind: string;
  created_at: string;
  summary_md: string;
  snapshot: {
    actions_total?: number;
    actions_new?: number;
    actions_by_type?: Record<string, number>;
    seo_score?: number | null;
    traction_mentions?: number | null;
    traction_strongest?: string | null;
    cost_usd?: number;
    total_tokens?: number | null;
    iterations?: number | null;
    deltas?: {
      actions_delta?: number;
      seo_delta?: number | null;
      traction_delta?: number | null;
    };
  };
};

export type LaunchScoreboard = {
  total_north: number;
  total_loop: number;
  total_visits: number;
  k: number;
  funnel_pct: number;
  tasks_done: number;
  tasks_total: number;
  tasks_pct: number;
};

export type LaunchAdvice = {
  move: string;
  rationale: string;
  rule_fired: string;
  scoreboard: LaunchScoreboard;
};

const API = "/api";

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

function ssePost(
  path: string,
  body: unknown,
  onEvent: (e: AgentEvent) => void,
): () => void {
  const ctrl = new AbortController();
  (async () => {
    let resp: Response;
    try {
      resp = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", message: String((err as Error).message || err) });
      }
      return;
    }
    if (!resp.ok || !resp.body) {
      onEvent({ type: "error", message: `${resp.status}` });
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        for (const line of block.split("\n")) {
          if (line.startsWith("data: ")) {
            try {
              const ev = JSON.parse(line.slice(6)) as AgentEvent;
              onEvent(ev);
              if (ev.type === "_done") {
                ctrl.abort();
                return;
              }
            } catch {
              // skip
            }
          }
        }
      }
    }
  })();
  return () => ctrl.abort();
}

export const api = {
  async health() {
    return json<{ ok: boolean; providers: string[] }>(await fetch(`${API}/health`));
  },

  // projects
  async listProjects() {
    return json<Project[]>(await fetch(`${API}/projects`));
  },
  async getProject(id: number) {
    return json<Project>(await fetch(`${API}/projects/${id}`));
  },
  async createProject(payload: { url: string; name?: string; description?: string; start_dive?: boolean }) {
    return json<Project>(
      await fetch(`${API}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    );
  },
  async updateProject(id: number, patch: Partial<Project>) {
    return json<Project>(
      await fetch(`${API}/projects/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
    );
  },
  // Fast pre-dive pass: crawl + propose a marketing brief the founder confirms.
  // Accepts an AbortSignal so the modal can cancel a stale/duplicate request
  // (React StrictMode fires effects twice in dev).
  async recon(projectId: number, signal?: AbortSignal) {
    return json<ReconResult>(
      await fetch(`${API}/projects/${projectId}/recon`, { method: "POST", signal }),
    );
  },
  // The LLM brief pre-fill, fetched in the background after recon (slow
  // reasoning models must not block the modal). Returns only fields it filled.
  async suggestBrief(projectId: number, signal?: AbortSignal) {
    return json<{ suggested: Partial<Brief> }>(
      await fetch(`${API}/projects/${projectId}/brief/suggest`, { method: "POST", signal }),
    );
  },
  // Complete, irreversible wipe of a project and everything it owns.
  async deleteProject(id: number) {
    return json<{ ok: boolean; deleted: number }>(
      await fetch(`${API}/projects/${id}`, { method: "DELETE" }),
    );
  },

  // runs
  async startRun(
    projectId: number,
    kind: "first_dive" | "daily" | "weekly" | "weekly_review" | "manual" | "targeted",
    instruction = "",
    extra?: { target?: TargetKind; topic?: string },
  ) {
    return json<{ run_id: number; stream_url: string }>(
      await fetch(`${API}/projects/${projectId}/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, instruction, ...(extra ?? {}) }),
      }),
    );
  },
  async getRun(runId: number) {
    return json<RunDetail>(await fetch(`${API}/runs/${runId}`));
  },
  async listRuns(projectId: number) {
    return json<RunSummary[]>(await fetch(`${API}/projects/${projectId}/runs`));
  },
  streamRun(runId: number, onEvent: (e: AgentEvent) => void): () => void {
    const es = new EventSource(`${API}/runs/${runId}/stream`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as AgentEvent;
        onEvent(data);
        if (data.type === "_done") es.close();
      } catch {
        // ignore
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  },

  // gtm loop (the bet -> this week's moves -> the call)
  async getGtm(projectId: number) {
    return json<GtmState>(await fetch(`${API}/projects/${projectId}/gtm`));
  },
  async submitWeeklyReview(projectId: number, snapshot: WeeklySnapshot) {
    return json<{ run_id: number; stream_url: string }>(
      await fetch(`${API}/projects/${projectId}/weekly/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(snapshot),
      }),
    );
  },
  async setGtmMoveDone(projectId: number, weekId: number, index: number, done: boolean) {
    return json<{ week: GtmWeek }>(
      await fetch(`${API}/projects/${projectId}/gtm/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ week_id: weekId, index, done }),
      }),
    );
  },

  // actions
  async listActions(projectId: number, status?: string) {
    const q = status ? `?status=${status}` : "";
    return json<Action[]>(await fetch(`${API}/projects/${projectId}/actions${q}`));
  },
  async getAction(actionId: number) {
    return json<Action>(await fetch(`${API}/actions/${actionId}`));
  },
  async updateAction(actionId: number, patch: { status?: Action["status"]; title?: string; content?: string; chosen_variant?: number }) {
    return json<Action>(
      await fetch(`${API}/actions/${actionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
    );
  },
  async expandAction(actionId: number) {
    return json<{ action_id: number; detail_md: string }>(
      await fetch(`${API}/actions/${actionId}/expand`, { method: "POST" }),
    );
  },

  // documents
  async listDocuments(projectId: number) {
    return json<ProjectDocument[]>(
      await fetch(`${API}/projects/${projectId}/documents`),
    );
  },
  async getDocumentByKind(projectId: number, kind: DocumentKind) {
    return json<ProjectDocument>(
      await fetch(`${API}/projects/${projectId}/documents/${kind}`),
    );
  },
  async updateDocument(
    documentId: number,
    patch: { title?: string; content_md?: string },
  ) {
    return json<ProjectDocument>(
      await fetch(`${API}/documents/${documentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
    );
  },
  async regenerateDocument(projectId: number, kind: DocumentKind) {
    return json<ProjectDocument>(
      await fetch(`${API}/projects/${projectId}/documents/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind }),
      }),
    );
  },

  // chat
  async listChatSessions(projectId: number) {
    return json<ChatSession[]>(await fetch(`${API}/projects/${projectId}/chat/sessions`));
  },
  async createChatSession(projectId: number, title = "New conversation") {
    return json<ChatSession>(
      await fetch(`${API}/projects/${projectId}/chat/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      }),
    );
  },
  async getChatSession(sessionId: number) {
    return json<ChatSessionDetail>(await fetch(`${API}/chat/sessions/${sessionId}`));
  },
  async renameChatSession(sessionId: number, title: string) {
    return json<ChatSession>(
      await fetch(`${API}/chat/sessions/${sessionId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      }),
    );
  },
  async deleteChatSession(sessionId: number) {
    return json<{ ok: boolean }>(
      await fetch(`${API}/chat/sessions/${sessionId}`, { method: "DELETE" }),
    );
  },
  sendChatMessage(sessionId: number, content: string, onEvent: (e: AgentEvent) => void): () => void {
    return ssePost(`/chat/sessions/${sessionId}/messages`, { content }, onEvent);
  },

  // settings / providers
  async getSettings() {
    return json<SettingsPayload>(await fetch(`${API}/settings`));
  },
  async saveProviders(providers: ProviderConfig[]) {
    return json<{ ok: boolean; providers: ProviderConfig[] }>(
      await fetch(`${API}/settings/providers`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ providers }),
      }),
    );
  },
  async probeProvider(base_url: string, api_key: string) {
    return json<{ ok: boolean; models?: number; sample?: string[]; error?: string }>(
      await fetch(`${API}/settings/providers/probe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url, api_key }),
      }),
    );
  },
  async fetchModels(base_url: string, api_key: string) {
    return json<{ ok: boolean; models?: string[]; error?: string }>(
      await fetch(`${API}/settings/providers/fetch-models`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url, api_key }),
      }),
    );
  },

  // launch mode
  async getLaunch(projectId: number) {
    return json<{ campaign: LaunchCampaign | null }>(
      await fetch(`${API}/projects/${projectId}/launch`),
    );
  },
  async startLaunch(projectId: number, intake?: LaunchIntake) {
    // auto-infers intake + classifies in one step
    return json<{ classification: LaunchClassification; campaign: LaunchCampaign }>(
      await fetch(`${API}/projects/${projectId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intake: intake ?? null }),
      }),
    );
  },
  async updateLaunch(
    projectId: number,
    patch: Partial<{
      state: LaunchCampaign["state"];
      archetype: LaunchArchetypeKey;
      intake: LaunchIntake;
      plan: LaunchPlan;
      start_date: string;
    }>,
  ) {
    return json<{ campaign: LaunchCampaign }>(
      await fetch(`${API}/projects/${projectId}/launch`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
    );
  },
  async classifyLaunch(projectId: number) {
    return json<{ classification: LaunchClassification; campaign: LaunchCampaign }>(
      await fetch(`${API}/projects/${projectId}/launch/classify`, { method: "POST" }),
    );
  },
  async generateLaunchPlan(projectId: number, archetype: LaunchArchetypeKey) {
    return json<{ plan: LaunchPlan; campaign: LaunchCampaign }>(
      await fetch(`${API}/projects/${projectId}/launch/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archetype }),
      }),
    );
  },
  async trackLaunch(projectId: number) {
    return json<LaunchAdvice>(
      await fetch(`${API}/projects/${projectId}/launch/track`, { method: "POST" }),
    );
  },
  async generateLaunchAsset(projectId: number, target: TargetKind, topic = "") {
    return json<{ run_id: number; stream_url: string }>(
      await fetch(`${API}/projects/${projectId}/launch/assets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, topic }),
      }),
    );
  },
  async draftLaunchContent(projectId: number, dayIndex: number, pieceIndex: number) {
    return json<{ piece: LaunchContentPiece; day_index: number; piece_index: number }>(
      await fetch(`${API}/projects/${projectId}/launch/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ day_index: dayIndex, piece_index: pieceIndex }),
      }),
    );
  },
  async deleteLaunch(projectId: number) {
    return json<{ ok: boolean }>(
      await fetch(`${API}/projects/${projectId}/launch`, { method: "DELETE" }),
    );
  },

  // versions
  async listVersions(projectId: number) {
    return json<{ versions: ProjectVersion[] }>(
      await fetch(`${API}/projects/${projectId}/versions`),
    );
  },

  // usage
  async getUsage(projectId?: number) {
    const q = projectId != null ? `?project_id=${projectId}` : "";
    return json<{ overall: UsageTotals; project: UsageTotals | null }>(
      await fetch(`${API}/usage${q}`),
    );
  },

  // geo + links audits
  async auditGeo(projectId: number) {
    return json<{ geo: GeoSummary | null }>(
      await fetch(`${API}/projects/${projectId}/audit/geo`, { method: "POST" }),
    );
  },
  async auditLinks(projectId: number) {
    return json<{ links: LinksSummary | null }>(
      await fetch(`${API}/projects/${projectId}/audit/links`, { method: "POST" }),
    );
  },

  // traction (digital footprint)
  async scanTraction(projectId: number) {
    return json<{ status: string }>(
      await fetch(`${API}/projects/${projectId}/traction/scan`, { method: "POST" }),
    );
  },
  async getTraction(projectId: number) {
    return json<{ traction: TractionSummary | null }>(
      await fetch(`${API}/projects/${projectId}/traction`),
    );
  },
};

export const ACTION_TYPE_LABEL: Record<ActionType, string> = {
  seo_fix: "SEO & GEO",
  tweet: "X Writer",
  hn_post: "Hacker News",
  linkedin: "LinkedIn Writer",
  article: "Articles",
  hn_opportunity: "Hacker News",
  reddit_opportunity: "Reddit",
  reddit_reply: "Reddit",
  market_gap: "Positioning",
  strategy: "Strategy",
};

export const ACTION_TYPE_ICON: Record<ActionType, string> = {
  seo_fix: "globe",
  tweet: "twitter",
  hn_post: "hacker-news",
  linkedin: "linkedin",
  article: "article",
  hn_opportunity: "hacker-news",
  reddit_opportunity: "reddit",
  reddit_reply: "reddit",
  market_gap: "gap",
  strategy: "compass",
};
