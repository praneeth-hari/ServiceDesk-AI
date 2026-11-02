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
  const now = typeof nowInput === 'object' ? nowInput : new Date(nowInput);
  const isResolvedOrClosed = ticket.status === 'resolved' || ticket.status === 'closed';

  const createdTime = new Date(ticket.created_at).getTime();
  const dueTime = ticket.due_at ? new Date(ticket.due_at).getTime() : null;
  const updatedTime = new Date(ticket.updated_at).getTime();

  // If resolved or closed
  if (isResolvedOrClosed) {
    // Backend doesn't have resolved_at; updated_at represents status transition to resolved/closed.
    // Check if updated_at was past due_at
    const wasOverdue = dueTime !== null && (updatedTime > dueTime || (ticket.is_overdue && !ticket.due_at));
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

