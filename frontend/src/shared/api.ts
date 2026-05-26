import { supabase } from "./supabaseClient";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface Me {
  user_id: string;
  email: string | null;
  display_name: string | null;
  role: "owner" | "va";
}

export interface Project {
  id: string;
  name: string;
  is_scratch: boolean;
  created_at: string;
}

export type RelationshipType =
  | "property_or_mechanism"
  | "use_case"
  | "effect_or_outcome"
  | "practical_commercial"
  | "research_or_trial"
  | "broader_class"
  | "peer_entity";

export interface Silo {
  id: string;
  session_id: string;
  name: string;
  rationale: string | null;
  relationship_type: RelationshipType;
  supporting_evidence: string | null;
  source: "llm_proposed" | "user_added" | "llm_proposed_then_user_edited";
  is_broader_class: boolean;
  is_gated_for_competitor_mining: boolean;
  created_at: string;
}

export interface SiloDiscovery {
  session_id: string;
  status: string;
  detected_audience: string | null;
  needs_disambiguation: boolean;
  interpretations: string[];
  degraded_notes: string[];
  silos: Silo[];
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  if (!token) throw new Error("Not authenticated");

  const resp = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const getMe = () => request<Me>("/me");
export const getProjects = () => request<Project[]>("/projects");

export interface CreateSessionBody {
  seed_keyword: string;
  project_id?: string;
  audience_hint?: string;
  disambiguation_hint?: string;
  topic_count?: number;
  coverage_mode?: "standard" | "comprehensive";
}

export const createSession = (body: CreateSessionBody) =>
  request<SiloDiscovery>("/sessions", { method: "POST", body: JSON.stringify(body) });

export const getSession = (id: string) => request<SiloDiscovery>(`/sessions/${id}`);

export const disambiguateSession = (id: string, choice: string) =>
  request<SiloDiscovery>(`/sessions/${id}/disambiguate`, {
    method: "POST",
    body: JSON.stringify({ choice }),
  });

export const overrideAudience = (id: string, detected_audience: string) =>
  request<SiloDiscovery>(`/sessions/${id}/audience`, {
    method: "PATCH",
    body: JSON.stringify({ detected_audience }),
  });

export const finalizeSilos = (id: string) =>
  request<{ finalized: boolean; topic_count: number }>(`/sessions/${id}/finalize`, {
    method: "POST",
  });

export interface AddTopicBody {
  name: string;
  rationale?: string;
  relationship_type?: RelationshipType;
  is_broader_class?: boolean;
}

export const addTopic = (sessionId: string, body: AddTopicBody) =>
  request<Silo>(`/sessions/${sessionId}/topics`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export interface EditTopicBody {
  name?: string;
  rationale?: string;
  relationship_type?: RelationshipType;
}

export const editTopic = (topicId: string, body: EditTopicBody) =>
  request<Silo>(`/topics/${topicId}`, { method: "PATCH", body: JSON.stringify(body) });

export const deleteTopic = (topicId: string) =>
  request<void>(`/topics/${topicId}`, { method: "DELETE" });

export interface PipelineTopicCount {
  topic_id: string;
  name: string;
  active: number;
  total: number;
  grouping_count: number;
}

export interface PipelineCounts {
  active: number;
  filtered_relevance: number;
  filtered_junk: number;
}

// The long pipeline steps run in the background and return this immediately;
// the UI then polls getSummary for status (running -> terminal).
export interface AsyncAck {
  status: string;
  session_id: string;
  relevance_threshold?: number;
}

export interface SummaryPlanTopic {
  topic_id: string;
  name: string;
  articles: number;
  gaps: number;
}

export interface PipelineSummary {
  status: string;
  last_error: string | null;
  expansion: {
    counts: PipelineCounts;
    topics: PipelineTopicCount[];
  };
  plan: {
    clusters: number;
    gaps: number;
    dropped: number;
    collisions: number;
    topics: SummaryPlanTopic[];
  } | null;
  architecture: { generated_at: string; is_user_edited: boolean } | null;
}

export interface Keyword {
  id: string;
  topic_id: string;
  keyword: string;
  sources: string[];
  status: string;
  relevance_score: number | null;
  created_at: string;
}

export const setDeepMine = (id: string, topic_ids: string[]) =>
  request<{ gated_topic_ids: string[]; topics: Silo[] }>(`/sessions/${id}/deep-mine`, {
    method: "POST",
    body: JSON.stringify({ topic_ids }),
  });

export const expandSession = (id: string) =>
  request<AsyncAck>(`/sessions/${id}/expand`, { method: "POST" });

export const planArticles = (id: string) =>
  request<AsyncAck>(`/sessions/${id}/plan-articles`, { method: "POST" });

export const getSummary = (id: string) =>
  request<PipelineSummary>(`/sessions/${id}/summary`);

export interface RegateBody {
  relevance_threshold?: number;
  clustering_edge_threshold?: number;
  clustering_resolution?: number;
}

export const regate = (id: string, body: RegateBody = {}) =>
  request<AsyncAck>(`/sessions/${id}/regate`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export interface ClusterPreviewConfig {
  edge_threshold: number;
  resolution: number;
  groupings: number;
  median_size: number;
  singletons: number;
  size_buckets: Record<string, number>;
}

export interface ClusterPreview {
  relevance_threshold: number;
  active_keywords: number;
  configs: ClusterPreviewConfig[];
}

export interface FanoutBody {
  confirm_cost?: boolean;
  relevance_threshold?: number;
  clustering_edge_threshold?: number;
  clustering_resolution?: number;
}

export interface FanoutEstimate {
  sub_anchors_total: number;
  sub_anchors_per_silo: Record<string, number>;
  cost_multiplier_range: [number, number];
  note: string;
}

export interface FanoutAck {
  status: string; // "estimate" (not started) | "running"
  session_id: string;
  estimate: FanoutEstimate;
}

// Recursive Fanout (PRD §7.7). Without confirm_cost it returns the cost
// estimate + sub-anchor plan and does NOT spend; resend with confirm_cost: true.
export const fanout = (id: string, body: FanoutBody = {}) =>
  request<FanoutAck>(`/sessions/${id}/fanout`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const clusterPreview = (
  id: string,
  body: { relevance_threshold?: number; configs?: [number, number][] } = {},
) =>
  request<ClusterPreview>(`/sessions/${id}/cluster-preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getKeywords = (id: string, topicId: string, limit = 200, status = "active") =>
  request<Keyword[]>(
    `/sessions/${id}/keywords?topic_id=${encodeURIComponent(topicId)}` +
      `&status=${encodeURIComponent(status)}&limit=${limit}`,
  );

// M6 site architecture (PRD §7.11). One pillar per article-bearing silo + the
// internal linking matrix. The full two-panel Architecture View is M7.
export interface ArchitecturePillar {
  topic_id: string;
  silo_name: string;
  title: string;
  target_keyword: string;
  summary: string;
  h2_outline: string[];
  supporting_article_ids: string[];
  lateral_pillar_links: string[];
  degraded: boolean;
}

export interface ArchitectureSupportingArticle {
  article_id: string;
  name: string;
  intent: string;
  parent_pillar_topic_id: string;
  lateral_article_links: string[];
}

export interface ArchitectureJson {
  seed_keyword: string;
  detected_audience: string;
  pillars: ArchitecturePillar[];
  supporting_articles: ArchitectureSupportingArticle[];
  skipped_silos: string[];
}

export interface SiteArchitecture {
  session_id: string;
  architecture_json: ArchitectureJson;
  generated_at: string;
  is_user_edited: boolean;
}

// Kicks off generation in the background; poll getSummary until
// summary.architecture is non-null, then call getArchitecture.
export const generateArchitecture = (id: string) =>
  request<AsyncAck>(`/sessions/${id}/architecture`, { method: "POST" });

export const getArchitecture = (id: string) =>
  request<SiteArchitecture>(`/sessions/${id}/architecture`);
