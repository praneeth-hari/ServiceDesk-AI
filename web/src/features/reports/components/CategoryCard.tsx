import React, { useState } from 'react';
import { ReportCard } from './ReportCard';
import type { TicketsByCategoryItem } from '../../../api/reports';
import type { TicketStatus } from '../../../api/types';
import { STATUS_ORDER } from '../reportData';

export interface CategoryCardProps {
  items: TicketsByCategoryItem[] | null;
  breakdownByStatus: boolean;
  onBreakdownChange: (breakdown: boolean) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

const STATUS_CONFIG: Record<TicketStatus, { label: string; color: string }> = {
  open: { label: 'Open', color: '#0F766E' },
  in_progress: { label: 'In Progress', color: '#5BB5AC' },
  waiting_on_requester: { label: 'Waiting', color: '#7C5CBF' },
  resolved: { label: 'Resolved', color: '#99D2CB' },
  closed: { label: 'Closed', color: '#6B7280' },
};

interface CategoryDisplayItem {
  category: string;
  total: number;
  counts?: Record<string, number>;
  segments: { status: TicketStatus | null; count: number }[];
}

export const CategoryCard: React.FC<CategoryCardProps> = ({
  items,
  breakdownByStatus,
  onBreakdownChange,
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

  // Process data for single vs stacked breakdown
  const { categories, maxTotal } = React.useMemo(() => {
    if (!items || items.length === 0) {
      return { categories: [] as CategoryDisplayItem[], maxTotal: 1 };
    }

    if (!breakdownByStatus) {
      const list: CategoryDisplayItem[] = items.map((it) => ({
        category: it.category,
        total: it.count,
        counts: {},
        segments: [{ status: null as TicketStatus | null, count: it.count }],
      }));
      // Sort by total desc
      list.sort((a, b) => b.total - a.total);
      const max = Math.max(...list.map((c) => c.total), 1);
      return { categories: list, maxTotal: max };
    } else {
      // Group by category
      const map = new Map<string, { total: number; counts: Record<string, number> }>();
      for (const it of items) {
        if (!map.has(it.category)) {
          map.set(it.category, { total: 0, counts: {} });
        }
        const entry = map.get(it.category)!;
        entry.total += it.count;
        if (it.status) {
          entry.counts[it.status] = (entry.counts[it.status] || 0) + it.count;
        }
      }

      const list: CategoryDisplayItem[] = Array.from(map.entries()).map(([cat, val]) => {
        const segments = STATUS_ORDER.map((st) => ({
          status: st as TicketStatus | null,
          count: val.counts[st] || 0,
        })).filter((s) => s.count > 0);

        return {
          category: cat,
          total: val.total,
          counts: val.counts,
          segments,
        };
      });

      // Sort by total desc
      list.sort((a, b) => b.total - a.total);
      const max = Math.max(...list.map((c) => c.total), 1);
      return { categories: list, maxTotal: max };
    }
  }, [items, breakdownByStatus]);

  const isEmpty = categories.length === 0 || categories.every((c) => c.total === 0);

  // SVG Geometry
  const width = 540;
  const barHeight = 22; // at most 24px thick
  const rowHeight = 36;
  const padLeft = 100;
  const padRight = 45;
  const padTop = 15;
  const padBottom = 20;

  const height = padTop + categories.length * rowHeight + padBottom;
  const plotWidth = width - padLeft - padRight;

  const toggleHeader = (
    <label className="flex items-center gap-1.5 text-xs text-ink cursor-pointer select-none">
      <input
        type="checkbox"
        checked={breakdownByStatus}
        onChange={(e) => onBreakdownChange(e.target.checked)}
        className="rounded border-line text-teal focus:ring-teal/30 h-3.5 w-3.5"
      />
      <span className="font-medium">Split by status</span>
    </label>
  );

  return (
    <ReportCard
      title="By category"
      subtitle={
        breakdownByStatus
          ? 'Ticket volume per category segmented by status'
          : 'Ranked ticket volume per category'
      }
      headerRight={toggleHeader}
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
            aria-label="Tickets by category table"
          >
            <thead>
              <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                <th className="py-2 px-3">Category</th>
                {breakdownByStatus ? (
                  <>
                    <th className="py-2 px-3 text-right">Open</th>
                    <th className="py-2 px-3 text-right">In Progress</th>
                    <th className="py-2 px-3 text-right">Waiting</th>
                    <th className="py-2 px-3 text-right">Resolved</th>
                    <th className="py-2 px-3 text-right">Closed</th>
                    <th className="py-2 px-3 text-right font-semibold">Total</th>
                  </>
                ) : (
                  <th className="py-2 px-3 text-right font-semibold">Count</th>
                )}
              </tr>
            </thead>
            <tbody>
              {categories.map((row) => (
                <tr
                  key={row.category}
                  className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                >
                  <td className="py-2 px-3 font-medium text-ink capitalize">
                    {row.category}
                  </td>
                  {breakdownByStatus ? (
                    <>
                      <td className="py-2 px-3 text-right text-muted">
                        {row.counts?.open || 0}
                      </td>
                      <td className="py-2 px-3 text-right text-muted">
                        {row.counts?.in_progress || 0}
                      </td>
                      <td className="py-2 px-3 text-right text-muted">
                        {row.counts?.waiting_on_requester || 0}
                      </td>
                      <td className="py-2 px-3 text-right text-muted">
                        {row.counts?.resolved || 0}
                      </td>
                      <td className="py-2 px-3 text-right text-muted">
                        {row.counts?.closed || 0}
                      </td>
                      <td className="py-2 px-3 text-right font-semibold text-ink">
                        {row.total}
                      </td>
                    </>
                  ) : (
                    <td className="py-2 px-3 text-right font-semibold text-ink">
                      {row.total}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative w-full">
          {/* Status Legend if split by status */}
          {breakdownByStatus && (
            <div className="flex items-center justify-end gap-3 mb-3 text-xs text-muted flex-wrap">
              {STATUS_ORDER.map((st) => (
                <div key={st} className="flex items-center gap-1.5">
                  <span
                    className="w-3 h-3 rounded-xs shrink-0"
                    style={{ backgroundColor: STATUS_CONFIG[st].color }}
                    aria-hidden="true"
                  />
                  <span>{STATUS_CONFIG[st].label}</span>
                </div>
              ))}
            </div>
          )}

          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto overflow-visible select-none"
            aria-label="Horizontal bar chart of tickets by category"
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

            {categories.map((row, rowIdx) => {
              const y = padTop + rowIdx * rowHeight;
              let currentX = padLeft;
              const totalWidth = maxTotal > 0 ? (row.total / maxTotal) * plotWidth : 0;

              return (
                <g key={row.category}>
                  {/* Category label */}
                  <text
                    x={padLeft - 10}
                    y={y + barHeight / 2 + 4}
                    textAnchor="end"
                    className="text-xs fill-ink font-medium capitalize"
                  >
                    {row.category}
                  </text>

                  {/* Single Hue or Stacked Segments */}
                  {!breakdownByStatus ? (
                    <rect
                      x={padLeft}
                      y={y}
                      width={Math.max(4, totalWidth)}
                      height={barHeight}
                      fill="#0F766E"
                      rx="4"
                      tabIndex={0}
                      role="button"
                      aria-label={`${row.category}: ${row.total} tickets`}
                      className="cursor-pointer transition-opacity hover:opacity-90 focus:opacity-90 outline-none"
                      onMouseEnter={() =>
                        setActiveTooltip({
                          text: `${row.category}: ${row.total} tickets`,
                          x: padLeft + totalWidth / 2,
                          y,
                        })
                      }
                      onMouseLeave={() => setActiveTooltip(null)}
                      onFocus={() =>
                        setActiveTooltip({
                          text: `${row.category}: ${row.total} tickets`,
                          x: padLeft + totalWidth / 2,
                          y,
                        })
                      }
                      onBlur={() => setActiveTooltip(null)}
                    >
                      <title>{`${row.category}: ${row.total} tickets`}</title>
                    </rect>
                  ) : (
                    row.segments.map((seg, sIdx) => {
                      const segWidth =
                        maxTotal > 0 ? (seg.count / maxTotal) * plotWidth : 0;
                      const isLast = sIdx === row.segments.length - 1;
                      const segW = Math.max(0, segWidth - (isLast ? 0 : 2));
                      const segX = currentX;
                      currentX += segWidth;

                      const stConfig = seg.status
                        ? STATUS_CONFIG[seg.status]
                        : { label: 'Total', color: '#0F766E' };
                      const label = `${row.category} · ${stConfig.label}: ${seg.count} tickets`;

                      return (
                        <rect
                          key={seg.status || sIdx}
                          x={segX}
                          y={y}
                          width={segW}
                          height={barHeight}
                          fill={stConfig.color}
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
                    })
                  )}

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
