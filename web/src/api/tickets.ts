import { apiFetch } from './client';
import {
  PaginatedTickets,
  Ticket,
  TicketListParams,
  TicketCreateRequest,
  Comment,
  CommentCreateRequest,
  StatusHistory,
  TicketStatus,
  SimilarTicket,
  User,
} from './types';

export async function listTickets(params: TicketListParams = {}): Promise<PaginatedTickets> {
  const searchParams = new URLSearchParams();

  if (params.page !== undefined && params.page !== null) {
    searchParams.set('page', params.page.toString());
  }
  if (params.page_size !== undefined && params.page_size !== null) {
    searchParams.set('page_size', params.page_size.toString());
  }
  if (params.status) {
    searchParams.set('status', params.status);
  }
  if (params.priority) {
    searchParams.set('priority', params.priority);
  }
  if (params.category) {
    searchParams.set('category', params.category);
  }
  if (params.assignee_id !== undefined && params.assignee_id !== null) {
    searchParams.set('assignee_id', params.assignee_id.toString());
  }
  if (params.overdue !== undefined && params.overdue !== null) {
    searchParams.set('overdue', params.overdue.toString());
  }
  if (params.q && params.q.trim()) {
    searchParams.set('q', params.q.trim());
  }
  if (params.sort_by) {
    searchParams.set('sort_by', params.sort_by);
  }
  if (params.order) {
    searchParams.set('order', params.order);
  }

  const queryString = searchParams.toString();
  const endpoint = queryString ? `/tickets?${queryString}` : '/tickets';
  return apiFetch<PaginatedTickets>(endpoint);
}

export async function getTicket(id: number): Promise<Ticket> {
  return apiFetch<Ticket>(`/tickets/${id}`);
}

export async function createTicket(input: TicketCreateRequest): Promise<Ticket> {
  return apiFetch<Ticket>('/tickets', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function listComments(ticketId: number): Promise<Comment[]> {
  return apiFetch<Comment[]>(`/tickets/${ticketId}/comments`);
}

export async function addComment(ticketId: number, input: CommentCreateRequest): Promise<Comment> {
  return apiFetch<Comment>(`/tickets/${ticketId}/comments`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function getHistory(ticketId: number): Promise<StatusHistory[]> {
  return apiFetch<StatusHistory[]>(`/tickets/${ticketId}/history`);
}

export async function changeStatus(ticketId: number, status: TicketStatus): Promise<Ticket> {
  return apiFetch<Ticket>(`/tickets/${ticketId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

export async function assignTicket(ticketId: number, assigneeId: number): Promise<Ticket> {
  return apiFetch<Ticket>(`/tickets/${ticketId}/assign`, {
    method: 'PATCH',
    body: JSON.stringify({ assignee_id: assigneeId }),
  });
}

export async function getSimilarTickets(ticketId: number, limit = 5): Promise<SimilarTicket[]> {
  return apiFetch<SimilarTicket[]>(`/tickets/${ticketId}/similar?limit=${limit}`);
}

export async function listAgents(): Promise<User[]> {
  const users = await apiFetch<User[]>('/users?skip=0&limit=100');
  return users.filter((u) => u.role === 'agent' && u.is_active);
}
