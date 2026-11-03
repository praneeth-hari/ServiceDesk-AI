import React, { useState } from 'react';
import { ReportCard } from './ReportCard';
import type { SLABreachRateItem } from '../../../api/reports';
import type { TicketPriority } from '../../../api/types';

export interface SlaCardProps {
  items: SLABreachRateItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

const PRIORITY_LABELS: Record<TicketPriority, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  urgent: 'Urgent',
};

const PRIORITY_ORDER: TicketPriority[] = ['low', 'medium', 'high', 'urgent'];

export const SlaCard: React.FC<SlaCardProps> = ({
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

  // Sort items by canonical priority order
  const sortedItems = React.useMemo(() => {
    if (!items) return [];
    const copy = [...items];
    copy.sort((a, b) => PRIORITY_ORDER.indexOf(a.priority) - PRIORITY_ORDER.indexOf(b.priority));
    return copy;
  }, [items]);

  const isEmpty = sortedItems.length === 0 || sortedItems.every((i) => i.total_tickets === 0);

  // SVG Geometry
  const width = 540;
  const barHeight = 22; // at most 24px thick
  const rowHeight = 38;
  const padLeft = 85;
  const padRight = 135; // space for breach rate text on right
  const padTop = 15;
  const padBottom = 20;

  const height = padTop + sortedItems.length * rowHeight + padBottom;
  const maxTotal = Math.max(...sortedItems.map((i) => i.total_tickets), 1);
  const plotWidth = width - padLeft - padRight;

  return (
    <ReportCard
      title="SLA by priority"
      subtitle="SLA compliance and breach rate segmented by priority"
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
            aria-label="SLA breach rate by priority table"
          >
            <thead>
              <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                <th className="py-2 px-3">Priority</th>
                <th className="py-2 px-3 text-right">Total</th>
                <th className="py-2 px-3 text-right">Met SLA</th>
                <th className="py-2 px-3 text-right">Breached SLA</th>
                <th className="py-2 px-3 text-right font-semibold">Breach Rate</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item) => (
                <tr
                  key={item.priority}
                  className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                >
                  <td className="py-2 px-3 font-medium text-ink">
                    {PRIORITY_LABELS[item.priority] || item.priority}
                  </td>
                  <td className="py-2 px-3 text-right text-ink font-medium">
                    {item.total_tickets}
                  </td>
                  <td className="py-2 px-3 text-right text-teal font-medium">
                    {item.met_sla}
                  </td>
                  <td className="py-2 px-3 text-right text-coral font-medium">
                    {item.breached_sla}
                  </td>
                  <td className="py-2 px-3 text-right font-semibold text-ink">
                    {item.breach_rate.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative w-full">
          {/* Legend naming both Met and Breached */}
          <div className="flex items-center justify-end gap-4 mb-3 text-xs text-muted">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-xs bg-teal shrink-0" aria-hidden="true" />
              <span>Met SLA</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-xs bg-coral shrink-0" aria-hidden="true" />
              <span>Breached SLA</span>
            </div>
          </div>

          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto overflow-visible select-none"
            aria-label="Stacked horizontal bar chart of SLA compliance and breach rate by priority"
            role="img"
          >
            {/* Hairline baseline */}
            <line
              x1={padLeft}
              y1={padTop - 5}
              x2={padLeft}
              y2={height - padBottom}
              stroke="#E4DED2"
              strokeWidth="1"
            />

            {sortedItems.map((item, idx) => {
              const y = padTop + idx * rowHeight;
              const metW =
                maxTotal > 0 ? (item.met_sla / maxTotal) * plotWidth : 0;
              const breachedW =
                maxTotal > 0 ? (item.breached_sla / maxTotal) * plotWidth : 0;
              const hasBreached = item.breached_sla > 0;
              const hasMet = item.met_sla > 0;

              const labelMet = `${PRIORITY_LABELS[item.priority]}: Met SLA (${item.met_sla})`;
              const labelBreached = `${PRIORITY_LABELS[item.priority]}: Breached SLA (${item.breached_sla})`;

              const totalW = metW + breachedW;

              return (
                <g key={item.priority}>
                  {/* Priority Label */}
                  <text
                    x={padLeft - 10}
                    y={y + barHeight / 2 + 4}
                    textAnchor="end"
                    className="text-xs fill-ink font-medium"
                  >
                    {PRIORITY_LABELS[item.priority] || item.priority}
                  </text>

                  {/* Empty state hairline */}
                  {item.total_tickets === 0 && (
                    <rect
                      x={padLeft}
                      y={y}
                      width="4"
                      height={barHeight}
                      fill="#E4DED2"
                      rx="2"
                    />
                  )}

                  {/* Met SLA Bar (Teal) */}
                  {hasMet && (
                    <rect
                      x={padLeft}
                      y={y}
                      width={Math.max(2, metW - (hasBreached ? 2 : 0))}
                      height={barHeight}
                      fill="#0F766E"
                      rx={!hasBreached ? 4 : 0}
                      tabIndex={0}
                      role="button"
                      aria-label={labelMet}
                      className="cursor-pointer transition-opacity hover:opacity-90 focus:opacity-90 outline-none"
                      onMouseEnter={() =>
                        setActiveTooltip({
                          text: labelMet,
                          x: padLeft + metW / 2,
                          y,
                        })
                      }
                      onMouseLeave={() => setActiveTooltip(null)}
                      onFocus={() =>
                        setActiveTooltip({
                          text: labelMet,
                          x: padLeft + metW / 2,
                          y,
                        })
                      }
                      onBlur={() => setActiveTooltip(null)}
                    >
                      <title>{labelMet}</title>
                    </rect>
                  )}

                  {/* Breached SLA Bar (Coral) */}
                  {hasBreached && (
                    <rect
                      x={padLeft + metW}
                      y={y}
                      width={Math.max(2, breachedW)}
                      height={barHeight}
                      fill="#E4572E"
                      rx="4"
                      tabIndex={0}
                      role="button"
                      aria-label={labelBreached}
                      className="cursor-pointer transition-opacity hover:opacity-90 focus:opacity-90 outline-none"
                      onMouseEnter={() =>
                        setActiveTooltip({
                          text: labelBreached,
                          x: padLeft + metW + breachedW / 2,
                          y,
                        })
                      }
                      onMouseLeave={() => setActiveTooltip(null)}
                      onFocus={() =>
                        setActiveTooltip({
                          text: labelBreached,
                          x: padLeft + metW + breachedW / 2,
                          y,
                        })
                      }
                      onBlur={() => setActiveTooltip(null)}
                    >
                      <title>{labelBreached}</title>
                    </rect>
                  )}

                  {/* Breach Rate as text on the right */}
                  <text
                    x={padLeft + totalW + 12}
                    y={y + barHeight / 2 + 4}
                    className="text-xs font-mono fill-ink font-semibold"
                  >
                    {item.total_tickets > 0
                      ? `${item.breach_rate.toFixed(1)}% breach rate`
                      : '—'}
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

