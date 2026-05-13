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

export type Project = {
  id: number;
  name: string;
  url: string;
  description: string | null;
  competitors: string[];
  brand_voice: { tone?: string; vocabulary?: string; rhythm?: string; taboo?: string[] } | null;
  schedule_hour: number;
  schedule_minute: number;
  timezone: string;
  writing_instructions: WritingInstructions | null;
  pagespeed_summary: PageSpeedSummary | null;
  seo_summary: SeoSummary | null;
  created_at: string;
  // computed by the server when fetched via GET /projects[/id]
  latest_run?: RunSummary | null;
  active_run_id?: number | null;
  action_counts?: Record<string, number>;
  initial_run_id?: number | null;
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

  // runs
  async startRun(
    projectId: number,
    kind: "first_dive" | "daily" | "manual" | "targeted",
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
