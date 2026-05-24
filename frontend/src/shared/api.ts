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

export interface ExpansionResult {
  expanded: boolean;
  keyword_count: number;
  counts: PipelineCounts;
  degraded_notes: string[];
  timed_out: boolean;
  topics: PipelineTopicCount[];
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
  request<ExpansionResult>(`/sessions/${id}/expand`, { method: "POST" });

export interface PlanTopicCount {
  topic_id: string;
  name: string;
  articles: number;
  gaps: number;
  dropped: number;
  degraded: boolean;
}

export interface PlanResult {
  planned: boolean;
  clusters: number;
  dropped: number;
  gaps: number;
  degraded: boolean;
  degraded_notes: string[];
  timed_out: boolean;
  collisions: number;
  topics: PlanTopicCount[];
}

export const planArticles = (id: string) =>
  request<PlanResult>(`/sessions/${id}/plan-articles`, { method: "POST" });

export const getKeywords = (id: string, topicId: string, limit = 200, status = "active") =>
  request<Keyword[]>(
    `/sessions/${id}/keywords?topic_id=${encodeURIComponent(topicId)}` +
      `&status=${encodeURIComponent(status)}&limit=${limit}`,
  );
