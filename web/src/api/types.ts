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
