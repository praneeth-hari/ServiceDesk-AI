import React, { useState, useEffect, useCallback, useId } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/useAuth';
import { getAIQualityReport } from '../../api/client';
import type { AIQualityReportResponse } from '../../api/types';
import { ReportCard } from '../reports/components/ReportCard';

export const AIQualityPage: React.FC = () => {
  const { role } = useAuth();

  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<AIQualityReportResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [chartViewMode, setChartViewMode] = useState<'chart' | 'table'>('chart');

  const filterId = useId();

  const handleDaysChange = useCallback((newDays: number) => {
    setDays(newDays);
    setLoading(true);
    setReloadKey((k) => k + 1);
  }, []);

  const handleRetry = useCallback(() => {
    setLoading(true);
    setReloadKey((k) => k + 1);
  }, []);

  useEffect(() => {
    let ignore = false;

    if (role === 'requester') {
      return;
    }

    const load = async () => {
      try {
        const report = await getAIQualityReport(days);
        if (!ignore) {
          setData(report);
          setError(null);
        }
      } catch {
        if (!ignore) {
          setError('Failed to load AI quality report');
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    };

    load();

    return () => {
      ignore = true;
    };
  }, [days, reloadKey, role]);

  // If requester, redirect away to /tickets
  if (role === 'requester') {
    return <Navigate to="/tickets" replace />;
  }

  const isEmpty = !loading && !error && (!data || data.total_suggestions === 0);

  // Time range selector buttons
  const timeRangeControls = (
    <div className="flex items-center gap-1 bg-paper2 rounded p-0.5 border border-line">
      {[7, 30, 90].map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => handleDaysChange(opt)}
          className={`px-2 py-0.5 text-xs font-medium rounded transition-colors focus:outline-none focus:ring-1 focus:ring-teal ${
            days === opt
              ? 'bg-teal text-paper shadow-xs font-semibold'
              : 'text-muted hover:text-ink'
          }`}
          aria-label={`Show ${opt} days`}
        >
          {opt}d
        </button>
      ))}
    </div>
  );

  // SVG Chart Geometry
  const width = 560;
  const height = 220;
  const padLeft = 45;
  const padRight = 35;
  const padTop = 25;
  const padBottom = 35;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;

  const weeklyList = data?.weekly || [];

  const getX = (idx: number, total: number) => {
    if (total <= 1) return padLeft + plotWidth / 2;
    return padLeft + (idx / (total - 1)) * plotWidth;
  };

  const getY = (val: number) => {
    const clamped = Math.max(0, Math.min(100, val));
    return padTop + plotHeight - (clamped / 100) * plotHeight;
  };

  // Skip null data points (do not draw as 0)
  const requesterSeries = weeklyList
    .map((item, idx) => ({
      week: item.week_start,
      val: item.requester_category_acceptance_pct,
      x: getX(idx, weeklyList.length),
      y: item.requester_category_acceptance_pct !== null ? getY(item.requester_category_acceptance_pct) : 0,
    }))
    .filter((pt) => pt.val !== null);

  const agentSeries = weeklyList
    .map((item, idx) => ({
      week: item.week_start,
      val: item.agent_category_agreement_pct,
      x: getX(idx, weeklyList.length),
      y: item.agent_category_agreement_pct !== null ? getY(item.agent_category_agreement_pct) : 0,
    }))
    .filter((pt) => pt.val !== null);

  const requesterLinePath =
    requesterSeries.length > 0
      ? `M ${requesterSeries.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L ')}`
      : '';

  const agentLinePath =
    agentSeries.length > 0
      ? `M ${agentSeries.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L ')}`
      : '';

  const yTicks = [
    { label: '100%', y: padTop },
    { label: '50%', y: padTop + plotHeight / 2 },
    { label: '0%', y: padTop + plotHeight },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-line pb-4 gap-4">
        <div>
          <h1 className="font-serif text-3xl font-semibold text-ink">AI quality</h1>
          <p className="text-muted text-xs sm:text-sm mt-1">
            How often the triage suggestion is accepted by requesters and confirmed by agents. Live figures from the database.
          </p>
        </div>
        <div className="self-start sm:self-auto">{timeRangeControls}</div>
      </div>

      {/* Loading state skeleton */}
      {loading && (
        <div className="space-y-6 animate-pulse">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-paper border border-line rounded-lg p-4 h-28" />
            ))}
          </div>
          <div className="bg-paper border border-line rounded-lg p-6 h-72" />
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
        <div className="py-12 px-4 text-center rounded-lg bg-paper border border-line shadow-sm flex flex-col items-center justify-center">
          <p className="text-sm text-muted mb-4 font-medium">{error}</p>
          <button
            type="button"
            onClick={handleRetry}
            className="px-4 py-2 rounded bg-teal text-paper text-xs font-medium hover:bg-teal/90 transition-colors shadow-xs focus:outline-none focus:ring-1 focus:ring-teal"
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty State */}
      {isEmpty && (
        <div
          role="status"
          className="bg-paper border border-line rounded-lg p-12 text-center shadow-sm flex flex-col items-center justify-center gap-2"
        >
          <span className="font-serif text-lg font-semibold text-ink">No data yet</span>
          <p className="text-xs sm:text-sm text-muted max-w-md">
            No data yet. Figures appear once tickets are created with an AI triage suggestion.
          </p>
        </div>
      )}

      {/* Data Loaded */}
      {!loading && !error && data && data.total_suggestions > 0 && (
        <>
          {/* Four Stat Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Card 1: Suggestions made */}
            <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
              <span className="text-muted text-xs uppercase tracking-wider font-medium">
                Suggestions made
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-serif font-bold text-ink">
                  {data.total_suggestions}
                </span>
              </div>
              <span className="text-muted text-xs mt-1 font-mono">
                kNN: {data.counts_by_method['knn'] || 0} | LLM: {data.counts_by_method['llm-rag'] || 0}
              </span>
            </div>

            {/* Card 2: Requester kept AI category */}
            <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
              <span className="text-muted text-xs uppercase tracking-wider font-medium">
                Requester kept AI category
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-serif font-bold text-ink">
                  {data.requester_acceptance.category_pct !== null
                    ? `${data.requester_acceptance.category_pct}%`
                    : 'No data yet'}
                </span>
              </div>
              <span className="text-muted text-xs mt-1">
                {data.requester_acceptance.category_pct !== null
                  ? `${Math.round(
                      (data.requester_acceptance.category_pct * data.requester_acceptance.n) / 100
                    )} of ${data.requester_acceptance.n} tickets`
                  : '0 of 0 tickets'}
              </span>
            </div>

            {/* Card 3: Agents reviewed */}
            <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
              <span className="text-muted text-xs uppercase tracking-wider font-medium">
                Agents reviewed
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-serif font-bold text-ink">
                  {data.agent_review.reviewed_n}
                </span>
              </div>
              <span className="text-muted text-xs mt-1">
                {data.agent_review.confirmed_n} confirmed · {data.agent_review.corrected_n} corrected
              </span>
            </div>

            {/* Card 4: Agent agreement */}
            <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
              <span className="text-muted text-xs uppercase tracking-wider font-medium">
                Agent agreement
              </span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-serif font-bold text-ink">
                  {data.agent_review.category_agreement_pct !== null
                    ? `${data.agent_review.category_agreement_pct}%`
                    : 'No data yet'}
                </span>
              </div>
              <span className="text-muted text-xs mt-1">
                of {data.agent_review.reviewed_n} reviewed tickets
              </span>
            </div>
          </div>

          {/* Agreement over time (Line Chart / Table) */}
          <ReportCard
            title="Agreement over time"
            subtitle="Weekly trend of requester acceptance and agent agreement rates"
            viewMode={chartViewMode}
            onViewModeChange={setChartViewMode}
            hasTableView
          >
            {chartViewMode === 'table' ? (
              <div className="overflow-x-auto max-h-72">
                <table
                  className="w-full text-left text-xs border-collapse"
                  aria-label="Agreement over time table"
                >
                  <thead>
                    <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                      <th className="py-2 px-3">Week start</th>
                      <th className="py-2 px-3 text-right">Suggestions (n)</th>
                      <th className="py-2 px-3 text-right">Requester acceptance</th>
                      <th className="py-2 px-3 text-right">Agent agreement</th>
                    </tr>
                  </thead>
                  <tbody>
                    {weeklyList.map((item) => (
                      <tr
                        key={item.week_start}
                        className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                      >
                        <td className="py-2 px-3 font-mono text-ink">{item.week_start}</td>
                        <td className="py-2 px-3 text-right font-mono text-muted">{item.n}</td>
                        <td className="py-2 px-3 text-right font-medium text-ink">
                          {item.requester_category_acceptance_pct !== null
                            ? `${item.requester_category_acceptance_pct}%`
                            : '—'}
                        </td>
                        <td className="py-2 px-3 text-right font-medium text-ink">
                          {item.agent_category_agreement_pct !== null
                            ? `${item.agent_category_agreement_pct}%`
                            : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="relative w-full flex flex-col gap-3">
                {/* Chart Legend */}
                <div className="flex items-center gap-5 text-xs text-muted">
                  <div className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-[#0F766E] rounded inline-block" />
                    <span className="w-2 h-2 rounded-full bg-[#0F766E] inline-block -ml-2" />
                    <span className="font-medium text-ink">Requester acceptance</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-[#7C3AED] rounded inline-block" />
                    <span className="w-2 h-2 rounded-full bg-[#7C3AED] inline-block -ml-2" />
                    <span className="font-medium text-ink">Agent agreement</span>
                  </div>
                </div>

                <svg
                  viewBox={`0 0 ${width} ${height}`}
                  className="w-full h-auto overflow-visible select-none"
                  aria-label="Agreement over time line chart showing requester acceptance and agent agreement"
                  role="img"
                >
                  <defs>
                    <linearGradient id={`ai-wash-${filterId}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#0F766E" stopOpacity="0.15" />
                      <stop offset="100%" stopColor="#0F766E" stopOpacity="0.01" />
                    </linearGradient>
                  </defs>

                  {/* Horizontal Grid lines */}
                  {yTicks.map((tick, i) => (
                    <g key={i}>
                      <line
                        x1={padLeft}
                        y1={tick.y}
                        x2={width - padRight}
                        y2={tick.y}
                        stroke="#E4DED2"
                        strokeWidth="1"
                        strokeDasharray={i === 2 ? undefined : '2,2'}
                      />
                      <text
                        x={padLeft - 8}
                        y={tick.y + 4}
                        textAnchor="end"
                        className="text-[10px] fill-muted font-mono"
                      >
                        {tick.label}
                      </text>
                    </g>
                  ))}

                  {/* X Axis Ticks */}
                  {weeklyList.map((item, idx) => {
                    const x = getX(idx, weeklyList.length);
                    return (
                      <g key={item.week_start}>
                        <line
                          x1={x}
                          y1={padTop + plotHeight}
                          x2={x}
                          y2={padTop + plotHeight + 4}
                          stroke="#E4DED2"
                          strokeWidth="1"
                        />
                        <text
                          x={x}
                          y={padTop + plotHeight + 16}
                          textAnchor="middle"
                          className="text-[9px] fill-muted font-mono"
                        >
                          {item.week_start.slice(5)}
                        </text>
                      </g>
                    );
                  })}

                  {/* Requester acceptance line and dots */}
                  {requesterLinePath && (
                    <path
                      d={requesterLinePath}
                      fill="none"
                      stroke="#0F766E"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  )}
                  {requesterSeries.map((pt, i) => (
                    <circle
                      key={`req-${i}`}
                      cx={pt.x}
                      cy={pt.y}
                      r="3.5"
                      fill="#0F766E"
                      className="hover:r-5 transition-all"
                    >
                      <title>{`Requester acceptance: ${pt.val}% (${pt.week})`}</title>
                    </circle>
                  ))}

                  {/* Agent agreement line and dots */}
                  {agentLinePath && (
                    <path
                      d={agentLinePath}
                      fill="none"
                      stroke="#7C3AED"
                      strokeWidth="2"
                      strokeDasharray="4,3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  )}
                  {agentSeries.map((pt, i) => (
                    <circle
                      key={`agent-${i}`}
                      cx={pt.x}
                      cy={pt.y}
                      r="3.5"
                      fill="#7C3AED"
                      className="hover:r-5 transition-all"
                    >
                      <title>{`Agent agreement: ${pt.val}% (${pt.week})`}</title>
                    </circle>
                  ))}
                </svg>
              </div>
            )}
          </ReportCard>

          {/* Two-Column Grid: Top Corrections & By Method */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
            {/* Top Corrections Section */}
            <div className="bg-paper border border-line rounded-lg p-5 shadow-sm flex flex-col gap-4">
              <div>
                <h2 className="font-serif text-lg font-semibold text-ink">Top corrections</h2>
                <p className="text-muted text-xs mt-0.5">
                  Most frequent category overrides applied during agent review
                </p>
              </div>

              {data.top_corrections.length === 0 ? (
                <div className="py-8 text-center text-muted text-xs font-mono">
                  No corrections recorded yet.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table
                    className="w-full text-left text-xs border-collapse"
                    aria-label="Top category corrections"
                  >
                    <thead>
                      <tr className="border-b border-line text-muted font-medium bg-paper2/50">
                        <th className="py-2 px-3">Suggested</th>
                        <th className="py-2 px-3">Final</th>
                        <th className="py-2 px-3 text-right">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.top_corrections.map((corr, idx) => (
                        <tr
                          key={`${corr.suggested}-${corr.final}-${idx}`}
                          className="border-b border-line/60 hover:bg-paper2/40 transition-colors"
                        >
                          <td className="py-2 px-3 capitalize font-medium text-ink">
                            {corr.suggested}
                          </td>
                          <td className="py-2 px-3 capitalize font-medium text-ink">
                            {corr.final}
                          </td>
                          <td className="py-2 px-3 text-right font-mono font-medium text-ink">
                            {corr.count}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <p className="text-[11px] text-muted italic border-t border-line/60 pt-3">
                Only tickets an agent confirmed or corrected count as reviewed. Unreviewed tickets are excluded, not assumed correct.
              </p>
            </div>

            {/* By Method Section */}
            <div className="bg-paper border border-line rounded-lg p-5 shadow-sm flex flex-col gap-4">
              <div>
                <h2 className="font-serif text-lg font-semibold text-ink">By method</h2>
                <p className="text-muted text-xs mt-0.5">
                  Review agreement breakdown across different triage algorithms
                </p>
              </div>

              {(!data.by_method || data.by_method.length === 0) ? (
                <div className="py-8 text-center text-muted text-xs font-mono">
                  No method data available.
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  {data.by_method.map((item) => {
                    const badge = item.method.toLowerCase().includes('llm')
                      ? 'LLM'
                      : item.method.toLowerCase().includes('knn')
                      ? 'kNN'
                      : item.method.toUpperCase();

                    const pct = item.category_agreement_pct;

                    return (
                      <div
                        key={item.method}
                        className="bg-paper2/40 border border-line rounded p-3.5 flex flex-col gap-2"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold border bg-paper text-ink border-line">
                              {badge}
                            </span>
                            <span className="text-xs font-medium text-ink">
                              {item.reviewed_n > 0
                                ? `${pct ?? 0}% agreed · ${item.reviewed_n} reviewed`
                                : 'No reviews yet'}
                            </span>
                          </div>
                          <span className="text-[11px] font-mono text-muted">
                            {item.n} total
                          </span>
                        </div>

                        {/* Agreement Bar */}
                        <div className="w-full bg-paper3 rounded-full h-2 overflow-hidden">
                          <div
                            className="bg-teal h-full transition-all rounded-full"
                            style={{ width: `${item.reviewed_n > 0 && pct !== null ? pct : 0}%` }}
                            aria-label={`${badge} agreement rate: ${pct ?? 0}%`}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
