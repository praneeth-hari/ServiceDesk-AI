import { describe, it, expect } from 'vitest';
import { classifyTicketSla, sortTicketsDefault } from '../slaState';
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

  it('classifies resolved ticket as met when updated_at <= due_at (fallback when resolved_at is null)', () => {
    const resolvedTicket: Ticket = {
      ...baseTicket,
      status: 'resolved',
      resolved_at: null,
      updated_at: fromKolkataWallClock(2026, 9, 26, 14, 0, 0).toISOString(),
    };
    const now = fromKolkataWallClock(2026, 9, 26, 18, 0, 0);
    const result = classifyTicketSla(resolvedTicket, now);
    expect(result.category).toBe('met');
  });

  it('classifies resolved ticket as resolvedLate when updated_at > due_at (fallback when resolved_at is null)', () => {
    const resolvedLateTicket: Ticket = {
      ...baseTicket,
      status: 'resolved',
      resolved_at: null,
      updated_at: fromKolkataWallClock(2026, 9, 26, 18, 0, 0).toISOString(), // due was 17:00
    };
    const now = fromKolkataWallClock(2026, 9, 26, 19, 0, 0);
    const result = classifyTicketSla(resolvedLateTicket, now);
    expect(result.category).toBe('resolvedLate');
  });

  it('prefers resolved_at over updated_at when resolved_at <= due_at even if updated_at > due_at', () => {
    // Resolved at 14:00 (within 17:00 SLA), but closed/updated at 18:30 (after SLA)
    const resolvedTicket: Ticket = {
      ...baseTicket,
      status: 'closed',
      resolved_at: fromKolkataWallClock(2026, 9, 26, 14, 0, 0).toISOString(),
      updated_at: fromKolkataWallClock(2026, 9, 26, 18, 30, 0).toISOString(),
    };
    const now = fromKolkataWallClock(2026, 9, 26, 19, 0, 0);
    const result = classifyTicketSla(resolvedTicket, now);
    expect(result.category).toBe('met');
  });

  it('prefers resolved_at over updated_at when resolved_at > due_at even if updated_at is within SLA', () => {
    // Resolved at 18:00 (past 17:00 SLA)
    const resolvedLateTicket: Ticket = {
      ...baseTicket,
      status: 'resolved',
      resolved_at: fromKolkataWallClock(2026, 9, 26, 18, 0, 0).toISOString(),
      updated_at: fromKolkataWallClock(2026, 9, 26, 16, 0, 0).toISOString(),
    };
    const now = fromKolkataWallClock(2026, 9, 26, 19, 0, 0);
    const result = classifyTicketSla(resolvedLateTicket, now);
    expect(result.category).toBe('resolvedLate');
  });
});

describe('sortTicketsDefault', () => {
  const now = fromKolkataWallClock(2026, 9, 26, 12, 0, 0); // Mon 12:00 IST

  const makeTicket = (id: number, partial: Partial<Ticket>): Ticket => ({
    id,
    title: 'Ticket ' + id,
    description: 'desc',
    status: 'open',
    priority: 'medium',
    category: 'hardware',
    requester_id: 1,
    assignee_id: null,
    requester_name: 'Req',
    assignee_name: null,
    created_at: fromKolkataWallClock(2026, 9, 26, 9, 0, 0).toISOString(),
    due_at: fromKolkataWallClock(2026, 9, 26, 17, 0, 0).toISOString(),
    updated_at: fromKolkataWallClock(2026, 9, 26, 9, 0, 0).toISOString(),
    sla_paused_at: null,
    is_overdue: false,
    ...partial,
  });

  it('orders active tickets by severity: breached -> at risk -> paused -> on track -> resolved/closed', () => {
    const tResolved = makeTicket(1, {
      status: 'resolved',
      resolved_at: fromKolkataWallClock(2026, 9, 26, 11, 0, 0).toISOString(),
    });
    const tOnTrack = makeTicket(2, {
      // 3 hours elapsed of 8 hours = 37.5%
      created_at: fromKolkataWallClock(2026, 9, 26, 9, 0, 0).toISOString(),
      due_at: fromKolkataWallClock(2026, 9, 26, 17, 0, 0).toISOString(),
    });
    const tBreached = makeTicket(3, {
      // Due at 11:00, now is 12:00 -> breached
      due_at: fromKolkataWallClock(2026, 9, 26, 11, 0, 0).toISOString(),
    });
    const tAtRisk = makeTicket(4, {
      // 3 hours elapsed of 4 hours = 75% (09:00 to 13:00, now is 12:00)
      created_at: fromKolkataWallClock(2026, 9, 26, 9, 0, 0).toISOString(),
      due_at: fromKolkataWallClock(2026, 9, 26, 13, 0, 0).toISOString(),
    });
    const tPaused = makeTicket(5, {
      status: 'waiting_on_requester',
      sla_paused_at: fromKolkataWallClock(2026, 9, 26, 10, 0, 0).toISOString(),
    });

    const unsorted = [tResolved, tOnTrack, tBreached, tAtRisk, tPaused];
    const sorted = sortTicketsDefault(unsorted, now);

    expect(sorted.map((t) => t.id)).toEqual([3, 4, 5, 2, 1]);
  });

  it('orders within severity by due_at ascending (most overdue or soonest due first)', () => {
    // Two breached tickets: one due at 10:00 (more overdue), one due at 11:00 (less overdue)
    const tBreached10 = makeTicket(10, {
      due_at: fromKolkataWallClock(2026, 9, 26, 10, 0, 0).toISOString(),
    });
    const tBreached11 = makeTicket(11, {
      due_at: fromKolkataWallClock(2026, 9, 26, 11, 0, 0).toISOString(),
    });

    // Two atRisk tickets: one due at 12:30 (soonest due), one due at 13:00
    const tAtRisk1230 = makeTicket(12, {
      created_at: fromKolkataWallClock(2026, 9, 26, 4, 30, 0).toISOString(),
      due_at: fromKolkataWallClock(2026, 9, 26, 12, 30, 0).toISOString(),
    });
    const tAtRisk1300 = makeTicket(13, {
      created_at: fromKolkataWallClock(2026, 9, 26, 5, 0, 0).toISOString(),
      due_at: fromKolkataWallClock(2026, 9, 26, 13, 0, 0).toISOString(),
    });

    const sorted = sortTicketsDefault([tBreached11, tBreached10, tAtRisk1300, tAtRisk1230], now);
    expect(sorted.map((t) => t.id)).toEqual([10, 11, 12, 13]);
  });

  it('orders resolved and closed tickets newest resolved first', () => {
    const tResOld = makeTicket(21, {
      status: 'resolved',
      resolved_at: fromKolkataWallClock(2026, 9, 25, 10, 0, 0).toISOString(),
    });
    const tResNew = makeTicket(22, {
      status: 'resolved',
      resolved_at: fromKolkataWallClock(2026, 9, 26, 11, 0, 0).toISOString(),
    });
    const tClosed = makeTicket(23, {
      status: 'closed',
      resolved_at: fromKolkataWallClock(2026, 9, 26, 11, 30, 0).toISOString(),
      updated_at: fromKolkataWallClock(2026, 9, 26, 11, 30, 0).toISOString(),
    });

    const sorted = sortTicketsDefault([tResOld, tClosed, tResNew], now);
    expect(sorted.map((t) => t.id)).toEqual([23, 22, 21]);
  });
});
