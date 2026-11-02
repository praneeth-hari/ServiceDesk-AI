import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { Ticket } from '../../../api/types';
import { StatusBadge, PriorityBadge } from './Badges';
import {
  computeBusinessMinutesRemaining,
  formatSlaText,
} from '../businessTime';
import { classifyTicketSla } from '../slaState';

interface TableViewProps {
  tickets: Ticket[];
  isStaff: boolean;
  total: number;
  page: number;
  pageSize: number;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
  onSortChange: (sortBy: string) => void;
  onPageChange: (newPage: number) => void;
}

export const TableView: React.FC<TableViewProps> = ({
  tickets,
  isStaff,
  total,
  page,
  pageSize,
  sortBy,
  sortOrder,
  onSortChange,
  onPageChange,
}) => {
  const navigate = useNavigate();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Render initials circle for assignee
  const renderAssigneeAvatar = (name: string | null | undefined) => {
    if (!name) {
      return (
        <span className="inline-flex items-center gap-1.5 text-muted italic">
          <span className="w-6 h-6 rounded-full bg-paper2 border border-line flex items-center justify-center text-[10px] not-italic text-muted font-mono">
            —
          </span>
          <span>Unassigned</span>
        </span>
      );
    }

    const parts = name.trim().split(/\s+/);
    const initials =
      parts.length > 1
        ? `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase()
        : name.slice(0, 2).toUpperCase();

    return (
      <span className="inline-flex items-center gap-1.5 text-ink">
        <span className="w-6 h-6 rounded-full bg-tealLight/30 border border-teal/40 text-teal flex items-center justify-center text-[10px] font-bold">
          {initials}
        </span>
        <span className="truncate max-w-[140px]">{name}</span>
      </span>
    );
  };

  const renderSlaCell = (ticket: Ticket) => {
    const isPaused = ticket.status === 'waiting_on_requester' || ticket.sla_paused_at !== null;
    const remainingMins = computeBusinessMinutesRemaining(ticket.due_at);
    const slaText = formatSlaText(
      remainingMins,
      ticket.status,
      ticket.is_overdue || remainingMins < 0,
      isPaused
    );
    const sla = classifyTicketSla(ticket);

    return (
      <span className={`inline-flex items-center gap-1.5 font-mono text-xs font-medium ${sla.textClass}`}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: sla.colorHex }} />
        {slaText}
      </span>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Table Container */}
      <div className="border border-line rounded-lg bg-paper overflow-x-auto shadow-xs">
        <table className="w-full text-left border-collapse text-xs sm:text-sm">
          <thead>
            <tr className="bg-paper2 border-b border-line text-ink font-semibold">
              {/* ID */}
              <th scope="col" className="py-2.5 px-3 sm:px-4 w-20">
                <button
                  type="button"
                  onClick={() => onSortChange('id')}
                  className="flex items-center gap-1 text-ink hover:text-teal font-semibold focus:outline-none"
                  aria-label="Sort by ID"
                >
                  ID
                  <span className="text-[10px] text-muted">
                    {sortBy === 'id' ? (sortOrder === 'asc' ? '▲' : '▼') : '↕'}
                  </span>
                </button>
              </th>

              {/* Title */}
              <th scope="col" className="py-2.5 px-3 sm:px-4">
                Title
              </th>

              {/* Status */}
              <th scope="col" className="py-2.5 px-3 sm:px-4 w-28">
                Status
              </th>

              {/* Priority */}
              <th scope="col" className="py-2.5 px-3 sm:px-4 w-24">
                Priority
              </th>

              {/* Assignee (Staff only) */}
              {isStaff && (
                <th scope="col" className="py-2.5 px-3 sm:px-4 w-44">
                  Assignee
                </th>
              )}

              {/* SLA */}
              <th scope="col" className="py-2.5 px-3 sm:px-4 w-36">
                <button
                  type="button"
                  onClick={() => onSortChange('due_at')}
                  className="flex items-center gap-1 text-ink hover:text-teal font-semibold focus:outline-none"
                  aria-label="Sort by SLA Due Date"
                >
                  SLA
                  <span className="text-[10px] text-muted">
                    {sortBy === 'due_at' ? (sortOrder === 'asc' ? '▲' : '▼') : '↕'}
                  </span>
                </button>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {tickets.length === 0 ? (
              <tr>
                <td
                  colSpan={isStaff ? 6 : 5}
                  className="py-8 text-center text-muted font-sans"
                >
                  No tickets found
                </td>
              </tr>
            ) : (
              tickets.map((ticket) => (
                <tr
                  key={ticket.id}
                  tabIndex={0}
                  role="link"
                  aria-label={`Open ticket #${ticket.id}: ${ticket.title}`}
                  onClick={() => navigate(`/tickets/${ticket.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      navigate(`/tickets/${ticket.id}`);
                    }
                  }}
                  className="hover:bg-paper2/70 focus:bg-paper2/90 cursor-pointer transition-colors focus:outline-none"
                >
                  {/* ID */}
                  <td className="py-2.5 px-3 sm:px-4 font-mono font-medium text-ink">
                    #{ticket.id}
                  </td>

                  {/* Title */}
                  <td className="py-2.5 px-3 sm:px-4 text-ink font-medium max-w-xs sm:max-w-md truncate">
                    <span>{ticket.title}</span>
                  </td>

                  {/* Status */}
                  <td className="py-2.5 px-3 sm:px-4">
                    <StatusBadge status={ticket.status} />
                  </td>

                  {/* Priority */}
                  <td className="py-2.5 px-3 sm:px-4">
                    <PriorityBadge priority={ticket.priority} />
                  </td>

                  {/* Assignee (Staff only) */}
                  {isStaff && (
                    <td className="py-2.5 px-3 sm:px-4">
                      {renderAssigneeAvatar(ticket.assignee_name)}
                    </td>
                  )}

                  {/* SLA */}
                  <td className="py-2.5 px-3 sm:px-4 whitespace-nowrap">
                    {renderSlaCell(ticket)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      <div className="flex items-center justify-between px-1 py-2 text-xs sm:text-sm text-muted">
        <div>
          Showing {tickets.length > 0 ? (page - 1) * pageSize + 1 : 0}–
          {Math.min(total, page * pageSize)} of {total} tickets
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="px-3 py-1 rounded bg-paper border border-line text-ink disabled:opacity-40 disabled:cursor-not-allowed hover:not-disabled:border-teal transition-colors"
            aria-label="Previous page"
          >
            ← Previous
          </button>
          <span className="font-medium text-ink">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="px-3 py-1 rounded bg-paper border border-line text-ink disabled:opacity-40 disabled:cursor-not-allowed hover:not-disabled:border-teal transition-colors"
            aria-label="Next page"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
};

