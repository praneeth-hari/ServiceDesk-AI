import { apiFetch } from './client';
import type { TicketPriority, TicketStatus, TicketCategory } from './types';

export interface TicketsByStatusItem {
  status: TicketStatus;
  priority: TicketPriority;
  count: number;
}

export interface OverdueTicketItem {
  id: number;
  title: string;
  status: TicketStatus;
  priority: TicketPriority;
  due_at: string;
  requester_id: number;
  requester_name: string;
  assignee_id: number | null;
  assignee_name: string | null;
}

export interface ResolutionTimeItem {
  assignee_id: number;
  assignee_name: string;
  avg_resolution_hours: number;
  ticket_count: number;
}

export interface AgentRankingItem {
  rank: number;
  agent_id: number;
  agent_name: string;
  resolved_count: number;
}

export interface DailyVolumeItem {
  date: string;
  ticket_count: number;
}

export interface SLABreachRateItem {
  priority: TicketPriority;
  total_tickets: number;
  met_sla: number;
  breached_sla: number;
  breach_rate: number;
}

export interface ResolutionTimeByCategoryItem {
  category: TicketCategory | string;
  priority: TicketPriority;
  avg_resolution_hours: number;
  ticket_count: number;
}

export interface AgentWorkloadItem {
  agent_id: number;
  agent_name: string;
  open_tickets: number;
  overdue_tickets: number;
  resolved_tickets: number;
}

export interface TicketsByCategoryItem {
  category: TicketCategory | string;
  status: TicketStatus | null;
  count: number;
}

/** GET /api/v1/reports/tickets-by-status */
export async function getTicketsByStatus(): Promise<TicketsByStatusItem[]> {
  return apiFetch<TicketsByStatusItem[]>('/reports/tickets-by-status');
}

/** GET /api/v1/reports/overdue */
export async function getOverdueTickets(): Promise<OverdueTicketItem[]> {
  return apiFetch<OverdueTicketItem[]>('/reports/overdue');
}

/** GET /api/v1/reports/resolution-time */
export async function getResolutionTime(): Promise<ResolutionTimeItem[]> {
  return apiFetch<ResolutionTimeItem[]>('/reports/resolution-time');
}

/** GET /api/v1/reports/agent-ranking */
export async function getAgentRanking(): Promise<AgentRankingItem[]> {
  return apiFetch<AgentRankingItem[]>('/reports/agent-ranking');
}

/** GET /api/v1/reports/daily-volume?days=30 */
export async function getDailyVolume(days: number = 30): Promise<DailyVolumeItem[]> {
  return apiFetch<DailyVolumeItem[]>(`/reports/daily-volume?days=${days}`);
}

/** GET /api/v1/reports/sla-breach-rate */
export async function getSLABreachRate(): Promise<SLABreachRateItem[]> {
  return apiFetch<SLABreachRateItem[]>('/reports/sla-breach-rate');
}

/** GET /api/v1/reports/resolution-time-by-category */
export async function getResolutionTimeByCategory(): Promise<ResolutionTimeByCategoryItem[]> {
  return apiFetch<ResolutionTimeByCategoryItem[]>('/reports/resolution-time-by-category');
}

/** GET /api/v1/reports/agent-workload */
export async function getAgentWorkload(): Promise<AgentWorkloadItem[]> {
  return apiFetch<AgentWorkloadItem[]>('/reports/agent-workload');
}

export { getAIQualityReport } from './client';

/** GET /api/v1/reports/tickets-by-category?breakdown_by_status=false */
export async function getTicketsByCategory(
  breakdownByStatus: boolean = false
): Promise<TicketsByCategoryItem[]> {
  return apiFetch<TicketsByCategoryItem[]>(
    `/reports/tickets-by-category?breakdown_by_status=${breakdownByStatus}`
  );
}

