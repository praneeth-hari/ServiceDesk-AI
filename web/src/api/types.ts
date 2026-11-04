export type UserRole = 'requester' | 'agent' | 'admin';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface ApiErrorDetail {
  message: string;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

export type TicketStatus =
  | 'open'
  | 'in_progress'
  | 'waiting_on_requester'
  | 'resolved'
  | 'closed';

export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent';

export type TicketCategory =
  | 'network'
  | 'hardware'
  | 'software'
  | 'access'
  | 'email'
  | 'other';

export interface Ticket {
  id: number;
  title: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  category: TicketCategory;
  requester_id: number;
  assignee_id: number | null;
  requester_name: string | null;
  assignee_name: string | null;
  due_at: string | null;
  sla_paused_at: string | null;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
  is_overdue: boolean;
}

export interface PaginatedTickets {
  items: Ticket[];
  total: number;
  page: number;
  page_size: number;
}

export interface TicketListParams {
  page?: number;
  page_size?: number;
  status?: TicketStatus;
  priority?: TicketPriority;
  category?: TicketCategory;
  assignee_id?: number;
  overdue?: boolean;
  q?: string;
  sort_by?: 'created_at' | 'updated_at' | 'due_at';
  order?: 'asc' | 'desc';
}

export interface TriageSuggestionCreate {
  suggested_category: TicketCategory;
  suggested_priority: TicketPriority;
  method: string;
  embedder?: string | null;
}

export interface TicketCreateRequest {
  title: string;
  description: string;
  priority?: TicketPriority;
  category?: TicketCategory;
  triage_suggestion?: TriageSuggestionCreate;
}

export interface Comment {
  id: number;
  ticket_id: number;
  author_id: number;
  author_name?: string | null;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export interface CommentCreateRequest {
  body: string;
  is_internal?: boolean;
}

export interface StatusHistory {
  id: number;
  ticket_id: number;
  changed_by_id: number | null;
  actor_name?: string | null;
  from_status: TicketStatus | null;
  to_status: TicketStatus;
  created_at: string;
}

export interface TicketStatusUpdateRequest {
  status: TicketStatus;
}

export interface TicketAssignRequest {
  assignee_id: number;
}

export interface SimilarTicket {
  id: number;
  title: string;
  status: TicketStatus;
  category: TicketCategory;
  priority: TicketPriority;
  similarity: number;
}

export interface TriageSuggestRequest {
  title: string;
  description: string;
}

export interface TriageSuggestResponse {
  suggested_category: TicketCategory | null;
  suggested_priority: TicketPriority | null;
  confidence: number | null;
  evidence: SimilarTicket[];
  possible_duplicates: SimilarTicket[];
  embedder: string;
  method?: string;
  fallback_reason?: string | null;
}

export interface RequesterAcceptance {
  category_pct: number | null;
  priority_pct: number | null;
  n: number;
}

export interface AgentReview {
  reviewed_n: number;
  category_agreement_pct: number | null;
  priority_agreement_pct: number | null;
  confirmed_n?: number;
  corrected_n?: number;
}

export interface WeeklyAIQualityItem {
  week_start: string;
  n: number;
  requester_category_acceptance_pct: number | null;
  agent_category_agreement_pct: number | null;
}

export interface CategoryCorrectionItem {
  suggested: string;
  final: string;
  count: number;
}

export interface TriageFeedbackRead {
  id: number;
  ticket_id: number;
  method: string;
  embedder: string | null;
  suggested_category: string;
  suggested_priority: string;
  requester_category: string;
  requester_priority: string;
  final_category: string | null;
  final_priority: string | null;
  final_set_by: number | null;
  final_set_at: string | null;
  created_at: string;
}

export interface ByMethodItem {
  method: string;
  n: number;
  reviewed_n: number;
  category_agreement_pct: number | null;
}

export interface AIQualityReportResponse {
  total_suggestions: number;
  counts_by_method: Record<string, number>;
  requester_acceptance: RequesterAcceptance;
  agent_review: AgentReview;
  weekly: WeeklyAIQualityItem[];
  top_corrections: CategoryCorrectionItem[];
  by_method: ByMethodItem[];
}

export interface AIAssistStatusResponse {
  enabled: boolean;
  mode: 'off' | 'ollama';
  model: string | null;
}

export interface AIAssistFact {
  label: string;
  value: string;
}

export interface AIAssistSummaryResponse {
  task: 'summary';
  summary: string;
  facts: AIAssistFact[];
  dropped_fact_count?: number;
  model: string;
  latency_ms: number;
}

export interface AIAssistReplyResponse {
  task: 'reply';
  reply: string;
  model: string;
  latency_ms: number;
}

export type AIAssistResponse = AIAssistSummaryResponse | AIAssistReplyResponse;
