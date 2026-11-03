import { parseToUtcDate } from './businessTime';
import type { Ticket } from '../../api/types';
import { computeBusinessMinutesBetween } from './businessTime';

export type SlaCategory = 'onTrack' | 'atRisk' | 'breached' | 'paused' | 'met' | 'resolvedLate';

export interface SlaInfo {
  category: SlaCategory;
  label: string;
  colorHex: string;
  bgHex: string;
  textClass: string;
  bgClass: string;
  borderClass: string;
  elapsedMinutes: number;
  totalMinutes: number;
  ratio: number;
}

/**
 * Classifies a ticket into one of the 6 SLA categories:
 * - met: resolved or closed within SLA
 * - resolvedLate: resolved or closed after SLA due date
 * - paused: waiting_on_requester status or sla_paused_at is set
 * - breached: active and past due_at or is_overdue === true
 * - atRisk: active and >= 75% of business hours elapsed
 * - onTrack: active and < 75% of business hours elapsed
 */
export function classifyTicketSla(ticket: Ticket, nowInput: Date | string | number = new Date()): SlaInfo {
  const now = typeof nowInput === 'object' && nowInput instanceof Date ? nowInput : parseToUtcDate(nowInput);
  const isResolvedOrClosed = ticket.status === 'resolved' || ticket.status === 'closed';

  const createdTime = parseToUtcDate(ticket.created_at).getTime();
  const dueTime = ticket.due_at ? parseToUtcDate(ticket.due_at).getTime() : null;
  const resolvedOrUpdatedTime = ticket.resolved_at
    ? parseToUtcDate(ticket.resolved_at).getTime()
    : parseToUtcDate(ticket.updated_at).getTime();

  // If resolved or closed
  if (isResolvedOrClosed) {
    // Prefer resolved_at over updated_at when determining whether a ticket was resolved within SLA
    const wasOverdue =
      dueTime !== null &&
      (resolvedOrUpdatedTime > dueTime || (ticket.is_overdue && !ticket.due_at));
    if (wasOverdue) {
      return {
        category: 'resolvedLate',
        label: 'Resolved Late',
        colorHex: '#6B7280',
        bgHex: '#F2EDE3',
        textClass: 'text-muted',
        bgClass: 'bg-paper2',
        borderClass: 'border-muted/30',
        elapsedMinutes: 0,
        totalMinutes: 0,
        ratio: 1,
      };
    }
    return {
      category: 'met',
      label: 'SLA Met',
      colorHex: '#0F766E',
      bgHex: '#99D2CB33',
      textClass: 'text-teal',
      bgClass: 'bg-tealLight/20',
      borderClass: 'border-teal/30',
      elapsedMinutes: 0,
      totalMinutes: 0,
      ratio: 1,
    };
  }

  // If clock paused
  const isPaused = ticket.status === 'waiting_on_requester' || ticket.sla_paused_at !== null;
  if (isPaused) {
    return {
      category: 'paused',
      label: 'Clock Paused',
      colorHex: '#7C5CBF',
      bgHex: '#7C5CBF1A',
      textClass: 'text-purple',
      bgClass: 'bg-purple/10',
      borderClass: 'border-purple/30',
      elapsedMinutes: 0,
      totalMinutes: 0,
      ratio: 0,
    };
  }

  // Check if breached
  const isBreached = ticket.is_overdue || (dueTime !== null && now.getTime() > dueTime);
  if (isBreached) {
    return {
      category: 'breached',
      label: 'Breached',
      colorHex: '#E4572E',
      bgHex: '#E4572E1A',
      textClass: 'text-coral',
      bgClass: 'bg-coral/10',
      borderClass: 'border-coral/40',
      elapsedMinutes: 0,
      totalMinutes: 0,
      ratio: 1,
    };
  }

  // Active ticket: calculate ratio of elapsed business minutes vs total window
  if (dueTime && dueTime > createdTime) {
    const totalMinutes = computeBusinessMinutesBetween(createdTime, dueTime);
    const elapsedMinutes = computeBusinessMinutesBetween(createdTime, now);
    const ratio = totalMinutes > 0 ? elapsedMinutes / totalMinutes : 0;

    if (ratio >= 0.75) {
      return {
        category: 'atRisk',
        label: 'At Risk',
        colorHex: '#D99A00',
        bgHex: '#D99A001A',
        textClass: 'text-amber',
        bgClass: 'bg-amber/10',
        borderClass: 'border-amber/40',
        elapsedMinutes,
        totalMinutes,
        ratio: Math.min(1, Math.max(0, ratio)),
      };
    }

    return {
      category: 'onTrack',
      label: 'On Track',
      colorHex: '#0F766E',
      bgHex: '#99D2CB26',
      textClass: 'text-teal',
      bgClass: 'bg-tealLight/20',
      borderClass: 'border-teal/30',
      elapsedMinutes,
      totalMinutes,
      ratio: Math.min(1, Math.max(0, ratio)),
    };
  }

  // Fallback if no due time
  return {
    category: 'onTrack',
    label: 'On Track',
    colorHex: '#0F766E',
    bgHex: '#99D2CB26',
    textClass: 'text-teal',
    bgClass: 'bg-tealLight/20',
    borderClass: 'border-teal/30',
    elapsedMinutes: 0,
    totalMinutes: 0,
    ratio: 0,
  };
}

/**
 * Default sort order for tickets:
 * 1. Active tickets first, by severity: breached (0), at risk (1), paused (2), on track (3).
 *    Within each severity group: most overdue or soonest due first (due_at ascending).
 * 2. Resolved and closed tickets last (rank 4), newest resolved first (descending by resolved_at || updated_at).
 */
export function sortTicketsDefault(
  tickets: Ticket[],
  nowInput: Date | string | number = new Date()
): Ticket[] {
  const getSeverityRank = (ticket: Ticket): number => {
    const isResolvedOrClosed = ticket.status === 'resolved' || ticket.status === 'closed';
    if (isResolvedOrClosed) return 4;
    const sla = classifyTicketSla(ticket, nowInput);
    switch (sla.category) {
      case 'breached':
        return 0;
      case 'atRisk':
        return 1;
      case 'paused':
        return 2;
      case 'onTrack':
      default:
        return 3;
    }
  };

  return [...tickets].sort((a, b) => {
    const rankA = getSeverityRank(a);
    const rankB = getSeverityRank(b);

    if (rankA !== rankB) {
      return rankA - rankB;
    }

    // Both are resolved or closed
    if (rankA === 4) {
      const timeA = parseToUtcDate(a.resolved_at || a.updated_at).getTime();
      const timeB = parseToUtcDate(b.resolved_at || b.updated_at).getTime();
      return timeB - timeA;
    }

    // Both are active within the same severity group:
    // most overdue or soonest due first (due_at ascending)
    const dueA = a.due_at ? parseToUtcDate(a.due_at).getTime() : Infinity;
    const dueB = b.due_at ? parseToUtcDate(b.due_at).getTime() : Infinity;
    if (dueA !== dueB) {
      return dueA - dueB;
    }

    return a.id - b.id;
  });
}
