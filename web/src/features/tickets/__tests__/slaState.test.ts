import { describe, it, expect } from 'vitest';
import { classifyTicketSla } from '../slaState';
import { fromKolkataWallClock } from '../businessTime';
import type { Ticket } from '../../../api/types';

describe('classifyTicketSla pure function', () => {
  const baseTicket: Ticket = {
    id: 1,
    title: 'Test Ticket',
    description: 'Test description',
    status: 'open',
    priority: 'medium',
    category: 'hardware',
    requester_id: 10,
    assignee_id: 20,
    requester_name: 'Test Requester',
    assignee_name: 'Test Assignee',
    created_at: fromKolkataWallClock(2026, 9, 26, 9, 0, 0).toISOString(), // Mon 09:00 IST
    due_at: fromKolkataWallClock(2026, 9, 26, 17, 0, 0).toISOString(), // Mon 17:00 IST (8 business hours = 480 mins)
    updated_at: fromKolkataWallClock(2026, 9, 26, 9, 0, 0).toISOString(),
    sla_paused_at: null,
    is_overdue: false,
  };

  it('classifies ticket as onTrack when elapsed < 75%', () => {
    // 2 hours elapsed out of 8 hours = 25% < 75%
    const now = fromKolkataWallClock(2026, 9, 26, 11, 0, 0);
    const result = classifyTicketSla(baseTicket, now);
    expect(result.category).toBe('onTrack');
    expect(result.ratio).toBeCloseTo(0.25, 2);
  });

  it('classifies ticket as atRisk when elapsed >= 75%', () => {
    // 6.5 hours elapsed out of 8 hours = 81.25% >= 75%
    const now = fromKolkataWallClock(2026, 9, 26, 15, 30, 0);
    const result = classifyTicketSla(baseTicket, now);
    expect(result.category).toBe('atRisk');
    expect(result.ratio).toBeGreaterThanOrEqual(0.75);
  });

  it('classifies ticket as breached when now > due_at', () => {
    // 17:30 IST is past 17:00 IST due time
    const now = fromKolkataWallClock(2026, 9, 26, 17, 30, 0);
    const result = classifyTicketSla(baseTicket, now);
    expect(result.category).toBe('breached');
  });

  it('classifies ticket as breached when is_overdue is true', () => {
    const overdueTicket: Ticket = {
      ...baseTicket,
      is_overdue: true,
    };
    const now = fromKolkataWallClock(2026, 9, 26, 10, 0, 0);
    const result = classifyTicketSla(overdueTicket, now);
    expect(result.category).toBe('breached');
  });

  it('classifies ticket as paused when status is waiting_on_requester or sla_paused_at is set', () => {
    const waitingTicket: Ticket = {
      ...baseTicket,
      status: 'waiting_on_requester',
    };
    const pausedClockTicket: Ticket = {
      ...baseTicket,
      sla_paused_at: fromKolkataWallClock(2026, 9, 26, 10, 0, 0).toISOString(),
    };

    const now = fromKolkataWallClock(2026, 9, 26, 12, 0, 0);
    expect(classifyTicketSla(waitingTicket, now).category).toBe('paused');
    expect(classifyTicketSla(pausedClockTicket, now).category).toBe('paused');
  });

  it('classifies resolved ticket as met when updated_at <= due_at', () => {
    const resolvedTicket: Ticket = {
      ...baseTicket,
      status: 'resolved',
      updated_at: fromKolkataWallClock(2026, 9, 26, 14, 0, 0).toISOString(),
    };
    const now = fromKolkataWallClock(2026, 9, 26, 18, 0, 0);
    const result = classifyTicketSla(resolvedTicket, now);
    expect(result.category).toBe('met');
  });

  it('classifies resolved ticket as resolvedLate when updated_at > due_at', () => {
    const resolvedLateTicket: Ticket = {
      ...baseTicket,
      status: 'resolved',
      updated_at: fromKolkataWallClock(2026, 9, 26, 18, 0, 0).toISOString(), // due was 17:00
    };
    const now = fromKolkataWallClock(2026, 9, 26, 19, 0, 0);
    const result = classifyTicketSla(resolvedLateTicket, now);
    expect(result.category).toBe('resolvedLate');
  });
});

