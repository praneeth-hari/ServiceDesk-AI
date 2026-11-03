import React, { useState, useId } from 'react';
import { ReportCard } from './ReportCard';
import type { DailyVolumeItem } from '../../../api/reports';
import { fillDailySeries, filterOverlappingTicks } from '../reportData';

export interface DailyVolumeCardProps {
  items: DailyVolumeItem[] | null;
  days: number;
  onDaysChange: (days: number) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export const DailyVolumeCard: React.FC<DailyVolumeCardProps> = ({
  items,
  days,
  onDaysChange,
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

  const filterId = useId();

  // Full continuous date series ending today
  const series = React.useMemo(() => {
    if (!items) return [];
    return fillDailySeries(items, days);
  }, [items, days]);

  const isEmpty = series.length === 0 || series.every((s) => s.ticket_count === 0);

  // SVG Geometry with generous right padding (60px) so the "Latest" label never collides with lines or labels
  const width = 560;
  const height = 200;
  const padLeft = 40;
  const padRight = 60;
  const padTop = 30;
  const padBottom = 35;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;

  const maxCount = Math.max(...series.map((s) => s.ticket_count), 0);
  const niceMax = maxCount === 0 ? 5 : Math.ceil(maxCount / 5) * 5 || maxCount;

  // Find peak index
  let peakIdx = 0;
  for (let i = 0; i < series.length; i++) {
    if (series[i].ticket_count > series[peakIdx].ticket_count) {
      peakIdx = i;
    }
  }
  const lastIdx = series.length - 1;

  // Points coordinates
  const points = series.map((item, idx) => {
    const x =
      series.length > 1
        ? padLeft + (idx / (series.length - 1)) * plotWidth
        : padLeft + plotWidth / 2;
    const yRatio = niceMax > 0 ? item.ticket_count / niceMax : 0;
    const y = padTop + plotHeight - yRatio * plotHeight;
    return { ...item, x, y };
  });

  const linePath =
    points.length > 0
      ? `M ${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L ')}`
      : '';

  const baselineY = padTop + plotHeight;
  const areaPath =
    points.length > 0
      ? `M ${points[0].x.toFixed(1)},${baselineY} L ${points
          .map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
          .join(' L ')} L ${points[points.length - 1].x.toFixed(1)},${baselineY} Z`
      : '';

  // Clean Y ticks (0, mid, top)
  const yTicks = [
    { value: 0, y: baselineY },
    { value: Math.round(niceMax / 2), y: padTop + plotHeight / 2 },
    { value: niceMax, y: padTop },
  ];

  // X ticks every week (7 days) + last day
  const rawXTicks = points.filter((_, idx) => {
    return idx % 7 === 0 || idx === lastIdx;
  });

  const xTicks = filterOverlappingTicks(rawXTicks, 40);

  const dayOptions = [7, 30, 90];

  const headerControls = (
    <div className="flex items-center gap-1 bg-paper2 rounded p-0.5 border border-line">
      {dayOptions.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onDaysChange(opt)}
          className={`px-2 py-0.5 text-xs font-medium rounded transition-colors ${
            days === opt
              ? 'bg-teal text-paper shadow-xs'
              : 'text-muted hover:text-ink'
          }`}
          aria-label={`Show ${opt} days`}
        >
          {opt}d
        </button>
      ))}
    </div>
  );

  return (
    <ReportCard
      title="Tickets created per day"
      subtitle={`Daily creation volume over the past ${days} days (UTC)`}
      headerRight={headerControls}
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
        <div className="overflow-x-auto max-h-72">
          <table
            className="w-full text-left text-xs border-collapse"
            aria-label="Tickets created per day table"
          >
            <thead>
              <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                <th className="py-2 px-3">Date (UTC)</th>
                <th className="py-2 px-3 text-right">Tickets Created</th>
              </tr>
            </thead>
            <tbody>
              {series.map((item) => (
                <tr
                  key={item.date}
                  className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                >
                  <td className="py-2 px-3 font-mono text-ink">{item.date}</td>
                  <td className="py-2 px-3 text-right font-medium text-ink">
                    {item.ticket_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative w-full">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto overflow-visible select-none"
            aria-label={`Tickets created per day line chart over ${days} days, peak at ${series[peakIdx]?.ticket_count ?? 0} tickets`}
            role="img"
          >
            <defs>
              <linearGradient id={`daily-wash-${filterId}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0F766E" stopOpacity="0.20" />
                <stop offset="100%" stopColor="#0F766E" stopOpacity="0.02" />
              </linearGradient>
            </defs>

            {/* Hairline Grid lines */}
            {yTicks.map((tick, i) => (
              <g key={i}>
                <line
                  x1={padLeft}
                  y1={tick.y}
                  x2={width - padRight}
                  y2={tick.y}
                  stroke="#E4DED2"
                  strokeWidth="1"
                  strokeDasharray={i === 0 ? undefined : '2,2'}
                />
                <text
                  x={padLeft - 8}
                  y={tick.y + 4}
                  textAnchor="end"
                  className="text-[10px] fill-muted font-mono"
                >
                  {tick.value}
                </text>
              </g>
            ))}

            {/* X Axis ticks */}
            {xTicks.map((p, i) => (
              <g key={i}>
                <line
                  x1={p.x}
                  y1={baselineY}
                  x2={p.x}
                  y2={baselineY + 5}
                  stroke="#E4DED2"
                  strokeWidth="1"
                />
                <text
                  x={p.x}
                  y={baselineY + 18}
                  textAnchor="middle"
                  className="text-[9px] sm:text-[10px] fill-muted font-mono"
                >
                  {p.date.slice(5)}
                </text>
              </g>
            ))}

            {/* Soft Area Wash */}
            {areaPath && (
              <path d={areaPath} fill={`url(#daily-wash-${filterId})`} />
            )}

            {/* 2px Line */}
            {linePath && (
              <path
                d={linePath}
                fill="none"
                stroke="#0F766E"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {/* Peak Dot & Label */}
            {points[peakIdx] && points[peakIdx].ticket_count > 0 && (
              <g>
                <circle
                  cx={points[peakIdx].x}
                  cy={points[peakIdx].y}
                  r="4"
                  fill="#0F766E"
                />
                <text
                  x={points[peakIdx].x}
                  y={Math.max(12, points[peakIdx].y - 8)}
                  textAnchor="middle"
                  className="text-[10px] font-semibold fill-ink font-sans"
                >
                  Peak: {points[peakIdx].ticket_count}
                </text>
              </g>
            )}

            {/* Latest End Dot & Label placed safely to the right of the dot, never colliding with the line */}
            {points[lastIdx] && (
              <g>
                <circle
                  cx={points[lastIdx].x}
                  cy={points[lastIdx].y}
                  r="4"
                  fill="#0F766E"
                />
                <text
                  x={points[lastIdx].x + 8}
                  y={points[lastIdx].y + 3}
                  textAnchor="start"
                  className="text-[10px] font-semibold fill-ink font-sans"
                >
                  Latest: {points[lastIdx].ticket_count}
                </text>
              </g>
            )}

            {/* Focusable and Hoverable Marks for Tooltips */}
            {points.map((p, idx) => (
              <circle
                key={idx}
                cx={p.x}
                cy={p.y}
                r="6"
                tabIndex={0}
                role="button"
                aria-label={`${p.date}: ${p.ticket_count} tickets`}
                className="opacity-0 hover:opacity-100 focus:opacity-100 transition-opacity cursor-pointer fill-teal outline-none"
                onMouseEnter={() =>
                  setActiveTooltip({
                    text: `${p.date}: ${p.ticket_count} tickets`,
                    x: p.x,
                    y: p.y,
                  })
                }
                onMouseLeave={() => setActiveTooltip(null)}
                onFocus={() =>
                  setActiveTooltip({
                    text: `${p.date}: ${p.ticket_count} tickets`,
                    x: p.x,
                    y: p.y,
                  })
                }
                onBlur={() => setActiveTooltip(null)}
              >
                <title>{`${p.date}: ${p.ticket_count} tickets`}</title>
              </circle>
            ))}
          </svg>

          {/* Accessible Floating Tooltip */}
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
