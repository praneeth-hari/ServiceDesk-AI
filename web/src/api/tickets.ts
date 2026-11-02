import { apiFetch } from './client';
import { PaginatedTickets, Ticket, TicketListParams } from './types';

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

