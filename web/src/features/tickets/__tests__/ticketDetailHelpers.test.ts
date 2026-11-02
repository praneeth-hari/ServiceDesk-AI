import { describe, it, expect } from 'vitest';
import {
  resolveActorName,
  mergeTimeline,
  formatKolkataDetailTime,
  formatKolkataDueTime,
  getAllowedActions,
} from '../ticketDetailHelpers';
import type { Comment, StatusHistory } from '../../../api/types';

describe('ticketDetailHelpers', () => {
  const mockTicket = {
    requester_id: 10,
    requester_name: 'Alice Requester',
    assignee_id: 20,
    assignee_name: 'Bob Agent',
  };

  describe('resolveActorName', () => {
    it('returns "System" when actor is null or undefined', () => {
      expect(resolveActorName(null, mockTicket, 99)).toBe('System');
      expect(resolveActorName(undefined, mockTicket, 99)).toBe('System');
    });

    it('returns "You" when actor matches the current user ID', () => {
      // Current user is requester
      expect(resolveActorName(10, mockTicket, 10)).toBe('You');
      // Current user is assignee
      expect(resolveActorName(20, mockTicket, 20)).toBe('You');
      // Current user is third party staff
      expect(resolveActorName(30, mockTicket, 30)).toBe('You');
    });

    it('returns requester_name when actor matches ticket requester_id and is not current user', () => {
      expect(resolveActorName(10, mockTicket, 99)).toBe('Alice Requester');
    });

    it('returns assignee_name when actor matches ticket assignee_id and is not current user', () => {
      expect(resolveActorName(20, mockTicket, 99)).toBe('Bob Agent');
    });

    it('returns "Staff member" when actor is an unknown/unmatched ID', () => {
      expect(resolveActorName(88, mockTicket, 99)).toBe('Staff member');
    });
  });

  describe('mergeTimeline', () => {
    it('merges comments and history in ascending chronological order and preserves creation event', () => {
      const comments: Comment[] = [
        {
          id: 1,
          ticket_id: 1,
          author_id: 10,
          body: 'First comment',
          is_internal: false,
          created_at: '2026-10-25T10:05:00Z',
        },
        {
          id: 2,
          ticket_id: 1,
          author_id: 20,
          body: 'Second comment',
          is_internal: true,
          created_at: '2026-10-25T10:20:00Z',
        },
      ];

      const history: StatusHistory[] = [
        {
          id: 101,
          ticket_id: 1,
          changed_by_id: 10,
          from_status: null,
          to_status: 'open',
          created_at: '2026-10-25T10:00:00Z',
        },
        {
          id: 102,
          ticket_id: 1,
          changed_by_id: 20,
          from_status: 'open',
          to_status: 'in_progress',
          created_at: '2026-10-25T10:10:00Z',
        },
      ];

      const merged = mergeTimeline(comments, history);

      expect(merged).toHaveLength(4);
      expect(merged[0]).toEqual({
        kind: 'history',
        id: 101,
        created_at: '2026-10-25T10:00:00Z',
        history: history[0],
      });
      expect(merged[1]).toEqual({
        kind: 'comment',
        id: 1,
        created_at: '2026-10-25T10:05:00Z',
        comment: comments[0],
      });
      expect(merged[2]).toEqual({
        kind: 'history',
        id: 102,
        created_at: '2026-10-25T10:10:00Z',
        history: history[1],
      });
      expect(merged[3]).toEqual({
        kind: 'comment',
        id: 2,
        created_at: '2026-10-25T10:20:00Z',
        comment: comments[1],
      });
    });
  });

  describe('formatKolkataDetailTime and formatKolkataDueTime', () => {
    it('formats UTC ISO timestamp into Asia/Kolkata (+05:30) wall clock format', () => {
      // 2026-10-30T04:32:00Z -> 2026-10-30 10:02 IST (Friday)
      const formatted = formatKolkataDetailTime('2026-10-30T04:32:00Z');
      expect(formatted).toBe('Fri 30 Oct, 10:02');

      const dueFormatted = formatKolkataDueTime('2026-10-30T04:32:00Z');
      expect(dueFormatted).toBe('due Fri 30 Oct, 10:02 (business hours)');
    });
  });

  describe('getAllowedActions', () => {
    it('returns the correct transitions and confirmation requirements for each status', () => {
      expect(getAllowedActions('open')).toEqual([
        { targetStatus: 'in_progress', label: 'Start work' },
      ]);

      expect(getAllowedActions('in_progress')).toEqual([
        { targetStatus: 'waiting_on_requester', label: 'Waiting on requester' },
        { targetStatus: 'resolved', label: 'Resolve' },
      ]);

      expect(getAllowedActions('waiting_on_requester')).toEqual([
        { targetStatus: 'in_progress', label: 'Resume' },
      ]);

      expect(getAllowedActions('resolved')).toEqual([
        { targetStatus: 'closed', label: 'Close', confirmRequired: true },
        { targetStatus: 'in_progress', label: 'Reopen' },
      ]);

      expect(getAllowedActions('closed')).toEqual([]);
    });
  });
});

