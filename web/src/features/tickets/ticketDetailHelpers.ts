import type { Comment, StatusHistory, TicketStatus } from '../../api/types';
import { toKolkataWallClock } from './businessTime';

/**
 * Resolves author/actor display name from available ticket metadata and current user session.
 * NOTE: The backend CommentRead and StatusHistoryRead only return author_id / changed_by_id.
 * If the backend is updated in the future to return author_name or author_role directly,
 * this client-side resolver can be replaced.
 */
export function resolveActorName(
  actorId: number | null | undefined,
  ticket: {
    requester_id: number;
    requester_name: string | null;
    assignee_id: number | null;
    assignee_name: string | null;
  },
  currentUserId?: number | null
): string {
  if (actorId === null || actorId === undefined) {
    return 'System';
  }
  if (currentUserId !== null && currentUserId !== undefined && actorId === currentUserId) {
    return 'You';
  }
  if (actorId === ticket.requester_id) {
    return ticket.requester_name || 'Requester';
  }
  if (ticket.assignee_id !== null && actorId === ticket.assignee_id) {
    return ticket.assignee_name || 'Assignee';
  }
  return 'Staff member';
}

export type TimelineItem =
  | {
      kind: 'comment';
      id: number;
      created_at: string;
      comment: Comment;
    }
  | {
      kind: 'history';
      id: number;
      created_at: string;
      history: StatusHistory;
    };

/**
 * Merges comments and history into a chronological ascending activity stream.
 */
export function mergeTimeline(
  comments: Comment[],
  history: StatusHistory[]
): TimelineItem[] {
  const items: TimelineItem[] = [
    ...comments.map((c) => ({
      kind: 'comment' as const,
      id: c.id,
      created_at: c.created_at,
      comment: c,
    })),
    ...history.map((h) => ({
      kind: 'history' as const,
      id: h.id,
      created_at: h.created_at,
      history: h,
    })),
  ];

  return items.sort((a, b) => {
    const timeA = new Date(a.created_at).getTime();
    const timeB = new Date(b.created_at).getTime();
    if (timeA !== timeB) return timeA - timeB;
    // When timestamps match, place status history before comment
    if (a.kind !== b.kind) return a.kind === 'history' ? -1 : 1;
    return a.id - b.id;
  });
}

/**
 * Format Asia/Kolkata wall clock time like "Fri 30 Oct, 10:02"
 */
export function formatKolkataDetailTime(input: Date | string | number | null | undefined): string {
  if (!input) return '—';
  const kolkata = toKolkataWallClock(input);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const dayName = days[kolkata.getUTCDay()];
  const day = kolkata.getUTCDate();
  const month = months[kolkata.getUTCMonth()];
  const hours = String(kolkata.getUTCHours()).padStart(2, '0');
  const minutes = String(kolkata.getUTCMinutes()).padStart(2, '0');
  return `${dayName} ${day} ${month}, ${hours}:${minutes}`;
}

/**
 * Format due time: "due Mon 2 Nov, 17:00 (business hours)"
 */
export function formatKolkataDueTime(input: Date | string | number | null | undefined): string {
  if (!input) return '—';
  const formatted = formatKolkataDetailTime(input);
  return `due ${formatted} (business hours)`;
}

export interface AllowedAction {
  targetStatus: TicketStatus;
  label: string;
  confirmRequired?: boolean;
}

export function getAllowedActions(currentStatus: TicketStatus): AllowedAction[] {
  switch (currentStatus) {
    case 'open':
      return [{ targetStatus: 'in_progress', label: 'Start work' }];
    case 'in_progress':
      return [
        { targetStatus: 'waiting_on_requester', label: 'Waiting on requester' },
        { targetStatus: 'resolved', label: 'Resolve' },
      ];
    case 'waiting_on_requester':
      return [{ targetStatus: 'in_progress', label: 'Resume' }];
    case 'resolved':
      return [
        { targetStatus: 'closed', label: 'Close', confirmRequired: true },
        { targetStatus: 'in_progress', label: 'Reopen' },
      ];
    case 'closed':
      return [];
    default:
      return [];
  }
}

