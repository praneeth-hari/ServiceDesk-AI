import React, { useState } from 'react';
import { ReportCard } from './ReportCard';
import type { TicketsByStatusItem } from '../../../api/reports';
import type { TicketPriority, TicketStatus } from '../../../api/types';
import { statusPriorityMatrix, type StatusPriorityRow } from '../reportData';

export interface StatusPriorityCardProps {
  items: TicketsByStatusItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

const STATUS_LABELS: Record<TicketStatus, string> = {
  open: 'Open',
  in_progress: 'In Progress',
  waiting_on_requester: 'Waiting on Req.',
  resolved: 'Resolved',
  closed: 'Closed',
};

const PRIORITY_RAMP: Record<TicketPriority, { color: string; label: string }> = {
  low: { color: '#B2DFDB', label: 'Low' },
  medium: { color: '#4DB6AC', label: 'Medium' },
  high: { color: '#0F766E', label: 'High' },
  urgent: { color: '#064E48', label: 'Urgent' },
};

const PRIORITIES: TicketPriority[] = ['low', 'medium', 'high', 'urgent'];

export const StatusPriorityCard: React.FC<StatusPriorityCardProps> = ({
  items,
  loading,
  error,
  onRetry,
}) => {
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');
  const [activeTooltip, setActiveTooltip] = useState<{
    text: string;
    x: number;
    y: number;
  } | null>(null);

  const rows: StatusPriorityRow[] = React.useMemo(() => {
    if (!items) return [];
    return statusPriorityMatrix(items);
  }, [items]);

  const isEmpty = rows.length === 0 || rows.every((r) => r.total === 0);

  // SVG Layout dimensions
  const width = 540;
  const barHeight = 22; // at most 24px thick
  const rowHeight = 36;
  const padLeft = 110;
  const padRight = 45;
  const padTop = 15;
  const padBottom = 20;

  const height = padTop + rows.length * rowHeight + padBottom;
  const maxTotal = Math.max(...rows.map((r) => r.total), 1);
  const plotWidth = width - padLeft - padRight;

  return (
    <ReportCard
      title="Tickets by status"
      subtitle="Current status segmented by priority ramp"
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={isEmpty}
      emptyMessage="No tickets yet"
      viewMode={viewMode}
      onViewModeChange={setViewMode}
      hasTableView
    >
      {viewMode === 'table' ? (
        <div className="overflow-x-auto">
          <table
            className="w-full text-left text-xs border-collapse"
            aria-label="Tickets by status and priority table"
          >
            <thead>
              <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3 text-right">Low</th>
                <th className="py-2 px-3 text-right">Medium</th>
                <th className="py-2 px-3 text-right">High</th>
                <th className="py-2 px-3 text-right">Urgent</th>
                <th className="py-2 px-3 text-right font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.status}
                  className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                >
                  <td className="py-2 px-3 font-medium text-ink">
                    {STATUS_LABELS[row.status] || row.status}
                  </td>
                  <td className="py-2 px-3 text-right text-muted">{row.low}</td>
                  <td className="py-2 px-3 text-right text-muted">{row.medium}</td>
                  <td className="py-2 px-3 text-right text-muted">{row.high}</td>
                  <td className="py-2 px-3 text-right text-muted">{row.urgent}</td>
                  <td className="py-2 px-3 text-right font-semibold text-ink">
                    {row.total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative w-full">
          {/* Priority Legend */}
          <div className="flex items-center justify-end gap-3 mb-3 text-xs text-muted flex-wrap">
            {PRIORITIES.map((p) => (
              <div key={p} className="flex items-center gap-1.5">
                <span
                  className="w-3 h-3 rounded-xs shrink-0"
                  style={{ backgroundColor: PRIORITY_RAMP[p].color }}
                  aria-hidden="true"
                />
                <span>{PRIORITY_RAMP[p].label}</span>
              </div>
            ))}
          </div>

          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto overflow-visible select-none"
            aria-label="Horizontal stacked bar chart of tickets by status and priority"
            role="img"
          >
            {/* Hairline grid line at baseline */}
            <line
              x1={padLeft}
              y1={padTop - 5}
              x2={padLeft}
              y2={height - padBottom}
              stroke="#E4DED2"
              strokeWidth="1"
            />

            {rows.map((row, rowIdx) => {
              const y = padTop + rowIdx * rowHeight;
              let currentX = padLeft;

              // Find non-zero segments to determine last segment for rounding
              const segments = PRIORITIES.map((p) => ({
                priority: p,
                count: row[p],
                width: maxTotal > 0 ? (row[p] / maxTotal) * plotWidth : 0,
              })).filter((s) => s.count > 0);

              const totalWidth =
                maxTotal > 0 ? (row.total / maxTotal) * plotWidth : 0;

              return (
                <g key={row.status}>
                  {/* Status Label on left */}
                  <text
                    x={padLeft - 10}
                    y={y + barHeight / 2 + 4}
                    textAnchor="end"
                    className="text-xs fill-ink font-medium"
                  >
                    {STATUS_LABELS[row.status] || row.status}
                  </text>

                  {/* Empty bar track hairline */}
                  {row.total === 0 && (
                    <rect
                      x={padLeft}
                      y={y}
                      width="4"
                      height={barHeight}
                      fill="#E4DED2"
                      rx="2"
                    />
                  )}

                  {/* Stacked Segments */}
                  {segments.map((seg, sIdx) => {
                    const isLast = sIdx === segments.length - 1;
                    const segW = Math.max(0, seg.width - (isLast ? 0 : 2));
                    const segX = currentX;
                    currentX += seg.width;

                    const label = `${STATUS_LABELS[row.status]}: ${PRIORITY_RAMP[seg.priority].label} (${seg.count})`;

                    return (
                      <rect
                        key={seg.priority}
                        x={segX}
                        y={y}
                        width={segW}
                        height={barHeight}
                        fill={PRIORITY_RAMP[seg.priority].color}
                        // 4px rounded data ends on outer end of last segment, square bases
                        rx={isLast ? 4 : 0}
                        tabIndex={0}
                        role="button"
                        aria-label={label}
                        className="cursor-pointer transition-opacity hover:opacity-90 focus:opacity-90 outline-none"
                        onMouseEnter={() =>
                          setActiveTooltip({
                            text: label,
                            x: segX + segW / 2,
                            y,
                          })
                        }
                        onMouseLeave={() => setActiveTooltip(null)}
                        onFocus={() =>
                          setActiveTooltip({
                            text: label,
                            x: segX + segW / 2,
                            y,
                          })
                        }
                        onBlur={() => setActiveTooltip(null)}
                      >
                        <title>{label}</title>
                      </rect>
                    );
                  })}

                  {/* Total at bar end */}
                  <text
                    x={padLeft + totalWidth + 8}
                    y={y + barHeight / 2 + 4}
                    className="text-xs fill-ink font-semibold"
                  >
                    {row.total}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Floating Tooltip */}
          {activeTooltip && (
            <div
              className="absolute pointer-events-none z-10 -translate-x-1/2 -translate-y-full mb-2 px-2.5 py-1 rounded bg-ink text-paper text-xs font-mono shadow-md whitespace-nowrap"
              style={{
                left: `${(activeTooltip.x / width) * 100}%`,
                top: `${(activeTooltip.y / height) * 100}%`,
              }}
            >
              {activeTooltip.text}
            </div>
          )}
        </div>
      )}
    </ReportCard>
  );
};

