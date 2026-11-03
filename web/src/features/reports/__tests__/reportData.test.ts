import { describe, it, expect } from 'vitest';
import {
  kpis,
  fillDailySeries,
  mergeAgents,
  statusPriorityMatrix,
  categoryHeat,
  filterOverlappingTicks,
} from '../reportData';
import type {
  TicketsByStatusItem,
  OverdueTicketItem,
  SLABreachRateItem,
  DailyVolumeItem,
  AgentRankingItem,
  AgentWorkloadItem,
  ResolutionTimeItem,
  ResolutionTimeByCategoryItem,
} from '../../../api/reports';

describe('reportData pure functions', () => {
  describe('kpis()', () => {
    it('calculates total tickets, open now, overdue count, and SLA met percent', () => {
      const ticketsByStatus: TicketsByStatusItem[] = [
        { status: 'open', priority: 'low', count: 5 },
        { status: 'in_progress', priority: 'medium', count: 3 },
        { status: 'waiting_on_requester', priority: 'high', count: 2 },
        { status: 'resolved', priority: 'low', count: 4 },
        { status: 'closed', priority: 'urgent', count: 6 },
      ];

      const overdue: OverdueTicketItem[] = [
        {
          id: 1,
          title: 'Issue 1',
          status: 'open',
          priority: 'urgent',
          due_at: '2026-10-20T10:00:00',
          requester_id: 1,
          requester_name: 'Alice',
          assignee_id: null,
          assignee_name: null,
        },
        {
          id: 2,
          title: 'Issue 2',
          status: 'in_progress',
          priority: 'high',
          due_at: '2026-10-21T10:00:00',
          requester_id: 2,
          requester_name: 'Bob',
          assignee_id: 3,
          assignee_name: 'Charlie',
        },
      ];

      const sla: SLABreachRateItem[] = [
        { priority: 'low', total_tickets: 10, met_sla: 9, breached_sla: 1, breach_rate: 10 },
        { priority: 'urgent', total_tickets: 10, met_sla: 7, breached_sla: 3, breach_rate: 30 },
      ];

      const res = kpis(ticketsByStatus, overdue, sla);
      expect(res.totalTickets).toBe(20);
      expect(res.openNow).toBe(10); // 5 + 3 + 2
      expect(res.overdue).toBe(2);
      expect(res.slaMetPercent).toBe('80%'); // 16 / 20 = 80%
      expect(res.slaMetRatio).toBe('16 of 20 tickets');
    });

    it('handles empty SLA total by showing a dash', () => {
      const res = kpis([], [], []);
      expect(res.totalTickets).toBe(0);
      expect(res.openNow).toBe(0);
      expect(res.overdue).toBe(0);
      expect(res.slaMetPercent).toBe('-');
      expect(res.slaMetRatio).toBe('-');
    });

    it('handles undefined and null inputs gracefully', () => {
      const res = kpis(null, null, null);
      expect(res.totalTickets).toBe(0);
      expect(res.openNow).toBe(0);
      expect(res.overdue).toBe(0);
      expect(res.slaMetPercent).toBe('-');
      expect(res.slaMetRatio).toBe('-');
    });
  });

  describe('fillDailySeries()', () => {
    it('creates a complete consecutive sequence ending today with zeros for missing days', () => {
      const today = '2026-11-02';
      const items: DailyVolumeItem[] = [
        { date: '2026-10-31', ticket_count: 5 },
        { date: '2026-11-02', ticket_count: 3 },
      ];

      const result = fillDailySeries(items, 5, today);
      expect(result).toHaveLength(5);
      expect(result).toEqual([
        { date: '2026-10-29', ticket_count: 0 },
        { date: '2026-10-30', ticket_count: 0 },
        { date: '2026-10-31', ticket_count: 5 },
        { date: '2026-11-01', ticket_count: 0 },
        { date: '2026-11-02', ticket_count: 3 },
      ]);
    });

    it('handles empty inputs and generates zeros across the whole window', () => {
      const today = '2026-11-02';
      const result = fillDailySeries([], 3, today);
      expect(result).toHaveLength(3);
      expect(result.every((d) => d.ticket_count === 0)).toBe(true);
      expect(result[2].date).toBe('2026-11-02');
      expect(result[1].date).toBe('2026-11-01');
      expect(result[0].date).toBe('2026-10-31');
    });
  });

  describe('mergeAgents()', () => {
    it('joins ranking, workload, and resolution time sorted by rank', () => {
      const ranking: AgentRankingItem[] = [
        { rank: 1, agent_id: 10, agent_name: 'Asha Agent', resolved_count: 12 },
        { rank: 2, agent_id: 20, agent_name: 'Bob Agent', resolved_count: 8 },
      ];

      const workload: AgentWorkloadItem[] = [
        {
          agent_id: 10,
          agent_name: 'Asha Agent',
          open_tickets: 4,
          overdue_tickets: 1,
          resolved_tickets: 12,
        },
        {
          agent_id: 20,
          agent_name: 'Bob Agent',
          open_tickets: 6,
          overdue_tickets: 0,
          resolved_tickets: 8,
        },
      ];

      const resolution: ResolutionTimeItem[] = [
        { assignee_id: 10, assignee_name: 'Asha Agent', avg_resolution_hours: 4.5, ticket_count: 12 },
        { assignee_id: 20, assignee_name: 'Bob Agent', avg_resolution_hours: 8.2, ticket_count: 8 },
      ];

      const merged = mergeAgents(ranking, workload, resolution);
      expect(merged).toHaveLength(2);
      expect(merged[0]).toEqual({
        agent_id: 10,
        agent_name: 'Asha Agent',
        rank: 1,
        open_tickets: 4,
        overdue_tickets: 1,
        resolved_tickets: 12,
        avg_resolution_hours: 4.5,
      });
      expect(merged[1]).toEqual({
        agent_id: 20,
        agent_name: 'Bob Agent',
        rank: 2,
        open_tickets: 6,
        overdue_tickets: 0,
        resolved_tickets: 8,
        avg_resolution_hours: 8.2,
      });
    });

    it('handles an agent missing from workload (substitutes 0 or dash)', () => {
      const ranking: AgentRankingItem[] = [
        { rank: 1, agent_id: 10, agent_name: 'Asha Agent', resolved_count: 5 },
      ];
      const workload: AgentWorkloadItem[] = []; // Asha missing from workload
      const resolution: ResolutionTimeItem[] = [
        { assignee_id: 10, assignee_name: 'Asha Agent', avg_resolution_hours: 3.2, ticket_count: 5 },
      ];

      const merged = mergeAgents(ranking, workload, resolution);
      expect(merged).toHaveLength(1);
      expect(merged[0].agent_id).toBe(10);
      expect(merged[0].rank).toBe(1);
      expect(merged[0].open_tickets).toBe(0);
      expect(merged[0].overdue_tickets).toBe(0);
      expect(merged[0].resolved_tickets).toBe(5); // fallback from ranking
      expect(merged[0].avg_resolution_hours).toBe(3.2);
    });

    it('handles an agent missing from resolution time (substitutes dash)', () => {
      const ranking: AgentRankingItem[] = [
        { rank: 1, agent_id: 10, agent_name: 'Asha Agent', resolved_count: 0 },
      ];
      const workload: AgentWorkloadItem[] = [
        {
          agent_id: 10,
          agent_name: 'Asha Agent',
          open_tickets: 2,
          overdue_tickets: 0,
          resolved_tickets: 0,
        },
      ];
      const resolution: ResolutionTimeItem[] = []; // No resolution data yet

      const merged = mergeAgents(ranking, workload, resolution);
      expect(merged).toHaveLength(1);
      expect(merged[0].avg_resolution_hours).toBe('-');
    });
  });

  describe('statusPriorityMatrix()', () => {
    it('orders rows by status and columns by priority', () => {
      const items: TicketsByStatusItem[] = [
        { status: 'open', priority: 'low', count: 2 },
        { status: 'open', priority: 'urgent', count: 1 },
        { status: 'resolved', priority: 'medium', count: 4 },
      ];

      const matrix = statusPriorityMatrix(items);
      expect(matrix).toHaveLength(5);
      expect(matrix.map((r) => r.status)).toEqual([
        'open',
        'in_progress',
        'waiting_on_requester',
        'resolved',
        'closed',
      ]);

      expect(matrix[0]).toEqual({
        status: 'open',
        low: 2,
        medium: 0,
        high: 0,
        urgent: 1,
        total: 3,
      });

      expect(matrix[1].total).toBe(0); // in_progress
      expect(matrix[3]).toEqual({
        status: 'resolved',
        low: 0,
        medium: 4,
        high: 0,
        urgent: 0,
        total: 4,
      });
    });
  });

  describe('categoryHeat()', () => {
    it('produces category by priority matrix with null for missing cells', () => {
      const items: ResolutionTimeByCategoryItem[] = [
        { category: 'hardware', priority: 'low', avg_resolution_hours: 1.5, ticket_count: 2 },
        { category: 'hardware', priority: 'high', avg_resolution_hours: 3.0, ticket_count: 1 },
      ];

      const heat = categoryHeat(items);
      expect(heat).toHaveLength(1);
      expect(heat[0]).toEqual({
        category: 'hardware',
        low: 1.5,
        medium: null,
        high: 3.0,
        urgent: null,
      });
    });

    it('handles any unknown category string the API returns', () => {
      const items: ResolutionTimeByCategoryItem[] = [
        { category: 'telecom_voip_special', priority: 'urgent', avg_resolution_hours: 0.5, ticket_count: 1 },
        { category: 'devops_cloud_infra', priority: 'medium', avg_resolution_hours: 12.4, ticket_count: 3 },
      ];

      const heat = categoryHeat(items);
      expect(heat).toHaveLength(2);
      expect(heat[0].category).toBe('telecom_voip_special');
      expect(heat[0].urgent).toBe(0.5);
      expect(heat[0].low).toBeNull();
      expect(heat[1].category).toBe('devops_cloud_infra');
      expect(heat[1].medium).toBe(12.4);
    });
  });

  describe('filterOverlappingTicks()', () => {
    it('always preserves first and last ticks while skipping overlapping neighbors', () => {
      const ticks = [
        { x: 40, label: '10-05' },
        { x: 158, label: '10-12' },
        { x: 276, label: '10-19' },
        { x: 394, label: '10-26' },
        { x: 513, label: '11-02' },
        { x: 530, label: '11-03' },
      ];

      const result = filterOverlappingTicks(ticks, 36);
      expect(result.map((t) => t.label)).toEqual([
        '10-05',
        '10-12',
        '10-19',
        '10-26',
        '11-03',
      ]);
    });

    it('returns all ticks if no collision exists', () => {
      const ticks = [
        { x: 40, label: 'A' },
        { x: 150, label: 'B' },
        { x: 260, label: 'C' },
      ];
      expect(filterOverlappingTicks(ticks, 36)).toEqual(ticks);
    });

    it('handles short lists gracefully', () => {
      expect(filterOverlappingTicks([{ x: 10 }])).toEqual([{ x: 10 }]);
      expect(filterOverlappingTicks([{ x: 10 }, { x: 15 }])).toEqual([{ x: 10 }, { x: 15 }]);
    });
  });
});
