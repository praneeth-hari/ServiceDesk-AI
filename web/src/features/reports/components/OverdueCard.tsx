import { parseToUtcDate } from '../../../features/tickets/businessTime';
import React from 'react';
import { Link } from 'react-router-dom';
import { ReportCard } from './ReportCard';
import type { OverdueTicketItem } from '../../../api/reports';
import type { TicketPriority } from '../../../api/types';

export interface OverdueCardProps {
  items: OverdueTicketItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

const PRIORITY_BADGES: Record<TicketPriority, { label: string; bg: string; text: string }> = {
  urgent: { label: 'Urgent', bg: 'bg-coral/15 border-coral/30', text: 'text-coral' },
  high: { label: 'High', bg: 'bg-amber/15 border-amber/30', text: 'text-amber' },
  medium: { label: 'Medium', bg: 'bg-teal/15 border-teal/30', text: 'text-teal' },
  low: { label: 'Low', bg: 'bg-paper2 border-line', text: 'text-muted' },
};

export const OverdueCard: React.FC<OverdueCardProps> = ({
  items,
  loading,
  error,
  onRetry,
}) => {
  // Ensure sorted oldest due first
  const sorted = React.useMemo(() => {
    if (!items) return [];
    const copy = [...items];
    copy.sort((a, b) => parseToUtcDate(a.due_at).getTime() - parseToUtcDate(b.due_at).getTime());
    return copy;
  }, [items]);

  const isEmpty = sorted.length === 0;

  return (
    <ReportCard
      title="Overdue now"
      subtitle="Tickets past their SLA due date requiring immediate attention"
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={isEmpty}
      emptyMessage="No overdue tickets"
      hasTableView={false}
      className="col-span-full"
    >
      <div className="overflow-x-auto max-h-96">
        <table
          className="w-full text-left text-xs border-collapse"
          aria-label="Overdue tickets list table"
        >
          <thead>
            <tr className="border-b border-line text-muted font-medium bg-paper2/50">
              <th className="py-2.5 px-3 w-16">ID</th>
              <th className="py-2.5 px-3">Title</th>
              <th className="py-2.5 px-3 w-28">Priority</th>
              <th className="py-2.5 px-3 w-40">Assignee</th>
              <th className="py-2.5 px-3 w-44 text-right">Due Date (UTC)</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((ticket) => {
              const pConfig = PRIORITY_BADGES[ticket.priority] || {
                label: ticket.priority,
                bg: 'bg-paper2 border-line',
                text: 'text-muted',
              };

              let formattedDue = ticket.due_at;
              try {
                const d = parseToUtcDate(ticket.due_at);
                if (!isNaN(d.getTime())) {
                  formattedDue = d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
                }
              } catch {
                // Keep raw string
              }

              return (
                <tr
                  key={ticket.id}
                  className="border-b border-line/60 hover:bg-paper2/40 transition-colors group"
                >
                  {/* ID */}
                  <td className="py-2.5 px-3 font-mono font-medium text-muted">
                    <Link
                      to={`/tickets/${ticket.id}`}
                      className="text-teal hover:underline font-semibold"
                    >
                      #{ticket.id}
                    </Link>
                  </td>

                  {/* Title */}
                  <td className="py-2.5 px-3">
                    <Link
                      to={`/tickets/${ticket.id}`}
                      className="font-medium text-ink hover:text-teal transition-colors line-clamp-1"
                    >
                      {ticket.title}
                    </Link>
                  </td>

                  {/* Priority */}
                  <td className="py-2.5 px-3">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${pConfig.bg} ${pConfig.text}`}
                    >
                      {pConfig.label}
                    </span>
                  </td>

                  {/* Assignee */}
                  <td className="py-2.5 px-3 text-muted">
                    {ticket.assignee_name ? (
                      <span className="text-ink font-medium">{ticket.assignee_name}</span>
                    ) : (
                      <span className="italic text-muted">unassigned</span>
                    )}
                  </td>

                  {/* Due Date */}
                  <td className="py-2.5 px-3 text-right font-mono text-coral font-medium">
                    {formattedDue}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ReportCard>
  );
};

