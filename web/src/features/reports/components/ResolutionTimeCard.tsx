import React, { useState } from 'react';
import { ReportCard } from './ReportCard';
import type { ResolutionTimeByCategoryItem } from '../../../api/reports';
import type { TicketPriority } from '../../../api/types';
import { categoryHeat, type CategoryHeatRow } from '../reportData';

export interface ResolutionTimeCardProps {
  items: ResolutionTimeByCategoryItem[] | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

const PRIORITIES: { key: TicketPriority; label: string }[] = [
  { key: 'low', label: 'Low' },
  { key: 'medium', label: 'Medium' },
  { key: 'high', label: 'High' },
  { key: 'urgent', label: 'Urgent' },
];

export const ResolutionTimeCard: React.FC<ResolutionTimeCardProps> = ({
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

  const rows: CategoryHeatRow[] = React.useMemo(() => {
    if (!items) return [];
    return categoryHeat(items);
  }, [items]);

  const isEmpty = rows.length === 0;

  // Find max resolution hours to scale teal sequential ramp
  const maxHours = React.useMemo(() => {
    let max = 0;
    for (const r of rows) {
      for (const p of PRIORITIES) {
        const val = r[p.key];
        if (typeof val === 'number' && val > max) {
          max = val;
        }
      }
    }
    return max > 0 ? max : 1;
  }, [rows]);

  return (
    <ReportCard
      title="Hours to resolve"
      subtitle="Average elapsed hours from creation to first resolution by category & priority"
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
            aria-label="Resolution time by category and priority table"
          >
            <thead>
              <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                <th className="py-2 px-3">Category</th>
                <th className="py-2 px-3 text-right">Low</th>
                <th className="py-2 px-3 text-right">Medium</th>
                <th className="py-2 px-3 text-right">High</th>
                <th className="py-2 px-3 text-right">Urgent</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.category}
                  className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                >
                  <td className="py-2 px-3 font-medium text-ink capitalize">
                    {row.category}
                  </td>
                  {PRIORITIES.map((p) => {
                    const val = row[p.key];
                    return (
                      <td key={p.key} className="py-2 px-3 text-right font-mono text-ink">
                        {typeof val === 'number' ? `${val.toFixed(1)}h` : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative w-full overflow-x-auto">
          {/* Visual Category x Priority Matrix Heatmap */}
          <div
            className="min-w-[420px] border border-line rounded-md overflow-hidden"
            role="region"
            aria-label="Heatmap grid of average resolution hours by category and priority"
          >
            {/* Header row */}
            <div className="grid grid-cols-5 bg-paper2/70 border-b border-line text-xs font-semibold text-muted text-center py-2">
              <div className="text-left px-3 text-ink">Category</div>
              {PRIORITIES.map((p) => (
                <div key={p.key}>{p.label}</div>
              ))}
            </div>

            {/* Matrix Data Rows */}
            {rows.map((row) => (
              <div
                key={row.category}
                className="grid grid-cols-5 border-b border-line/60 last:border-b-0 items-stretch"
              >
                {/* Category name */}
                <div className="px-3 py-3 text-xs font-medium text-ink capitalize flex items-center bg-paper2/20 border-r border-line/50">
                  {row.category}
                </div>

                {/* Cells */}
                {PRIORITIES.map((p) => {
                  const val = row[p.key];
                  const hasVal = typeof val === 'number';
                  const ratio = hasVal ? val / maxHours : 0;
                  // Sequential teal ramp: alpha from 0.15 to 0.85
                  const alpha = hasVal ? 0.15 + 0.70 * ratio : 0;
                  // Contrast check: dark text for light cells, light text for dark cells
                  const textColor =
                    hasVal && alpha >= 0.55 ? '#FBF8F3' : '#1F2937';
                  const cellBg = hasVal
                    ? `rgba(15, 118, 110, ${alpha.toFixed(2)})`
                    : 'transparent';

                  const label = `${row.category} · ${p.label}: ${
                    hasVal ? `${val.toFixed(1)}h` : 'No data'
                  }`;

                  return (
                    <div
                      key={p.key}
                      tabIndex={0}
                      role="button"
                      aria-label={label}
                      className="p-3 text-center text-xs font-mono font-medium border-r border-line/40 last:border-r-0 flex items-center justify-center transition-opacity hover:opacity-90 focus:opacity-90 outline-none cursor-pointer"
                      style={{
                        backgroundColor: cellBg,
                        color: hasVal ? textColor : '#6B7280',
                      }}
                      onMouseEnter={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        setActiveTooltip({
                          text: label,
                          x: rect.left + rect.width / 2,
                          y: rect.top,
                        });
                      }}
                      onMouseLeave={() => setActiveTooltip(null)}
                      onFocus={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        setActiveTooltip({
                          text: label,
                          x: rect.left + rect.width / 2,
                          y: rect.top,
                        });
                      }}
                      onBlur={() => setActiveTooltip(null)}
                    >
                      {hasVal ? `${val.toFixed(1)}h` : '—'}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>

          {/* Floating Tooltip */}
          {activeTooltip && (
            <div
              className="fixed pointer-events-none z-50 -translate-x-1/2 -translate-y-full mb-2 px-2.5 py-1 rounded bg-ink text-paper text-xs font-mono shadow-md whitespace-nowrap"
              style={{
                left: `${activeTooltip.x}px`,
                top: `${activeTooltip.y - 6}px`,
              }}
            >
              {activeTooltip.text}
            </div>
          )}

          {/* Muted legend below matrix */}
          <div className="flex items-center justify-between text-xs text-muted mt-3 px-1">
            <span>Numbers indicate average elapsed hours</span>
            <div className="flex items-center gap-2">
              <span>Fastest</span>
              <div
                className="w-16 h-2 rounded-xs"
                style={{
                  background:
                    'linear-gradient(to right, rgba(15, 118, 110, 0.15), rgba(15, 118, 110, 0.85))',
                }}
                aria-hidden="true"
              />
              <span>Slowest</span>
            </div>
          </div>
        </div>
      )}
    </ReportCard>
  );
};
