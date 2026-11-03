import type {
  TicketsByStatusItem,
  OverdueTicketItem,
  SLABreachRateItem,
  DailyVolumeItem,
  AgentRankingItem,
  AgentWorkloadItem,
  ResolutionTimeItem,
  ResolutionTimeByCategoryItem,
} from '../../api/reports';
import type { TicketPriority, TicketStatus } from '../../api/types';

export interface KpiSummary {
  totalTickets: number;
  openNow: number;
  overdue: number;
  slaMetPercent: string;
  slaMetRatio: string;
  slaMetNumerator: number;
  slaMetDenominator: number;
}

export const STATUS_ORDER: TicketStatus[] = [
  'open',
  'in_progress',
  'waiting_on_requester',
  'resolved',
  'closed',
];

export const PRIORITY_ORDER: TicketPriority[] = ['low', 'medium', 'high', 'urgent'];

/**
 * Computes high-level KPI metrics from ticketsByStatus, overdue, and slaBreachRate endpoints.
 */
export function kpis(
  ticketsByStatus?: TicketsByStatusItem[] | null,
  overdue?: OverdueTicketItem[] | null,
  slaBreachRate?: SLABreachRateItem[] | null
): KpiSummary {
  const statusItems = ticketsByStatus ?? [];
  const overdueItems = overdue ?? [];
  const slaItems = slaBreachRate ?? [];

  const totalTickets = statusItems.reduce((acc, item) => acc + (item.count || 0), 0);

  const openSet = new Set<TicketStatus>(['open', 'in_progress', 'waiting_on_requester']);
  const openNow = statusItems
    .filter((item) => openSet.has(item.status))
    .reduce((acc, item) => acc + (item.count || 0), 0);

  const overdueCount = overdueItems.length;

  const totalSla = slaItems.reduce((acc, item) => acc + (item.total_tickets || 0), 0);
  const metSla = slaItems.reduce((acc, item) => acc + (item.met_sla || 0), 0);

  let slaMetPercent = '-';
  let slaMetRatio = '-';

  if (totalSla > 0) {
    const rate = Math.round((metSla / totalSla) * 1000) / 10;
    slaMetPercent = `${rate.toFixed(rate % 1 === 0 ? 0 : 1)}%`;
    slaMetRatio = `${metSla} of ${totalSla} tickets`;
  }

  return {
    totalTickets,
    openNow,
    overdue: overdueCount,
    slaMetPercent,
    slaMetRatio,
    slaMetNumerator: metSla,
    slaMetDenominator: totalSla,
  };
}

/**
 * Returns a complete array of consecutive UTC dates ending today with zeros for missing days.
 */
export function fillDailySeries(
  items: DailyVolumeItem[] = [],
  days: number = 30,
  today?: Date | string
): DailyVolumeItem[] {
  let endDate: Date;

  if (typeof today === 'string') {
    const parts = today.split('-').map(Number);
    endDate = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
  } else if (today instanceof Date) {
    endDate = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
  } else {
    const now = new Date();
    endDate = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  }

  const countMap = new Map<string, number>();
  for (const item of items) {
    countMap.set(item.date, item.ticket_count);
  }

  const result: DailyVolumeItem[] = [];

  for (let i = days - 1; i >= 0; i--) {
    const current = new Date(endDate.getTime() - i * 86400000);
    const dateStr = current.toISOString().slice(0, 10);
    result.push({
      date: dateStr,
      ticket_count: countMap.get(dateStr) ?? 0,
    });
  }

  return result;
}

export interface MergedAgentRow {
  agent_id: number;
  agent_name: string;
  rank: number | '-';
  open_tickets: number | '-';
  overdue_tickets: number | '-';
  resolved_tickets: number | '-';
  avg_resolution_hours: number | '-';
}

/**
 * Joins agent-ranking, agent-workload, and resolution-time by agent id into
 * one table row per agent (missing parts become 0 or a dash), sorted by rank.
 */
export function mergeAgents(
  ranking: AgentRankingItem[] = [],
  workload: AgentWorkloadItem[] = [],
  resolution: ResolutionTimeItem[] = []
): MergedAgentRow[] {
  const rankingMap = new Map<number, AgentRankingItem>();
  for (const r of ranking) {
    rankingMap.set(r.agent_id, r);
  }

  const workloadMap = new Map<number, AgentWorkloadItem>();
  for (const w of workload) {
    workloadMap.set(w.agent_id, w);
  }

  const resolutionMap = new Map<number, ResolutionTimeItem>();
  for (const res of resolution) {
    resolutionMap.set(res.assignee_id, res);
  }

  // Collect all distinct agent IDs
  const allIds = new Set<number>();
  for (const r of ranking) allIds.add(r.agent_id);
  for (const w of workload) allIds.add(w.agent_id);
  for (const res of resolution) allIds.add(res.assignee_id);

  const rows: MergedAgentRow[] = [];

  for (const id of allIds) {
    const r = rankingMap.get(id);
    const w = workloadMap.get(id);
    const res = resolutionMap.get(id);

    const agent_name = r?.agent_name || w?.agent_name || res?.assignee_name || `Agent #${id}`;
    const rank: number | '-' = r !== undefined ? r.rank : '-';

    const open_tickets: number | '-' = w !== undefined ? w.open_tickets : 0;
    const overdue_tickets: number | '-' = w !== undefined ? w.overdue_tickets : 0;
    const resolved_tickets: number | '-' =
      w !== undefined ? w.resolved_tickets : r !== undefined ? r.resolved_count : 0;

    const avg_resolution_hours: number | '-' =
      res !== undefined && res.avg_resolution_hours !== null ? res.avg_resolution_hours : '-';

    rows.push({
      agent_id: id,
      agent_name,
      rank,
      open_tickets,
      overdue_tickets,
      resolved_tickets,
      avg_resolution_hours,
    });
  }

  // Sort by rank ascending (ranked first, then unranked by id)
  rows.sort((a, b) => {
    if (typeof a.rank === 'number' && typeof b.rank === 'number') {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return a.agent_id - b.agent_id;
    }
    if (typeof a.rank === 'number') return -1;
    if (typeof b.rank === 'number') return 1;
    return a.agent_id - b.agent_id;
  });

  return rows;
}

export interface StatusPriorityRow {
  status: TicketStatus;
  low: number;
  medium: number;
  high: number;
  urgent: number;
  total: number;
}

/**
 * Produces rows in the order open, in_progress, waiting_on_requester, resolved, closed,
 * with counts per priority in the order low, medium, high, urgent.
 */
export function statusPriorityMatrix(
  items: TicketsByStatusItem[] = []
): StatusPriorityRow[] {
  const map = new Map<string, number>();
  for (const item of items) {
    map.set(`${item.status}:${item.priority}`, item.count);
  }

  return STATUS_ORDER.map((st) => {
    const low = map.get(`${st}:low`) ?? 0;
    const medium = map.get(`${st}:medium`) ?? 0;
    const high = map.get(`${st}:high`) ?? 0;
    const urgent = map.get(`${st}:urgent`) ?? 0;
    const total = low + medium + high + urgent;

    return {
      status: st,
      low,
      medium,
      high,
      urgent,
      total,
    };
  });
}

export interface CategoryHeatRow {
  category: string;
  low: number | null;
  medium: number | null;
  high: number | null;
  urgent: number | null;
}

/**
 * Produces a category by priority matrix of avg_resolution_hours with null for missing cells.
 * Handles any category string the API returns.
 */
export function categoryHeat(
  items: ResolutionTimeByCategoryItem[] = []
): CategoryHeatRow[] {
  // Collect categories in order of appearance
  const categories: string[] = [];
  const seen = new Set<string>();

  for (const item of items) {
    if (!seen.has(item.category)) {
      seen.add(item.category);
      categories.push(item.category);
    }
  }

  const lookup = new Map<string, number>();
  for (const item of items) {
    lookup.set(`${item.category}:${item.priority}`, item.avg_resolution_hours);
  }

  return categories.map((cat) => ({
    category: cat,
    low: lookup.get(`${cat}:low`) ?? null,
    medium: lookup.get(`${cat}:medium`) ?? null,
    high: lookup.get(`${cat}:high`) ?? null,
    urgent: lookup.get(`${cat}:urgent`) ?? null,
  }));
}


/**
 * Filter tick points with an x coordinate so that adjacent labels do not overlap.
 * Always keeps the first and last ticks; if an intermediate tick is within minDistance
 * of its predecessor or the final tick, drops that intermediate tick.
 */
export function filterOverlappingTicks<T extends { x: number }>(
  ticks: T[],
  minDistance = 36
): T[] {
  if (ticks.length <= 2) return [...ticks];

  const first = ticks[0];
  const last = ticks[ticks.length - 1];
  const kept: T[] = [first];

  for (let i = 1; i < ticks.length - 1; i++) {
    const current = ticks[i];
    const prev = kept[kept.length - 1];

    if (
      current.x - prev.x >= minDistance &&
      last.x - current.x >= minDistance
    ) {
      kept.push(current);
    }
  }

  kept.push(last);
  return kept;
}
