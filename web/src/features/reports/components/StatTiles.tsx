import React from 'react';
import type { KpiSummary } from '../reportData';

export interface StatTilesProps {
  summary: KpiSummary | null;
  loading: boolean;
}

export const StatTiles: React.FC<StatTilesProps> = ({ summary, loading }) => {
  if (loading || !summary) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-paper border border-line rounded-lg p-4 animate-pulse space-y-2 shadow-sm"
          >
            <div className="h-3 bg-paper2 rounded w-1/2" />
            <div className="h-7 bg-paper2 rounded w-3/4" />
            <div className="h-3 bg-paper2 rounded w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {/* 1. Total Tickets */}
      <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
        <span className="text-muted text-xs uppercase tracking-wider font-medium">
          Total tickets
        </span>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-serif font-bold text-ink">
            {summary.totalTickets}
          </span>
        </div>
        <span className="text-muted text-xs mt-1">All time created tickets</span>
      </div>

      {/* 2. Open Now */}
      <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
        <span className="text-muted text-xs uppercase tracking-wider font-medium">
          Open now
        </span>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-serif font-bold text-ink">
            {summary.openNow}
          </span>
        </div>
        <span className="text-muted text-xs mt-1">Open, in progress, or waiting</span>
      </div>

      {/* 3. Overdue (Coral number with a warning icon, not colour alone) */}
      <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
        <div className="flex items-center justify-between">
          <span className="text-muted text-xs uppercase tracking-wider font-medium">
            Overdue
          </span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          {summary.overdue > 0 && (
            <svg
              aria-label="Warning: overdue tickets"
              role="img"
              className="w-6 h-6 text-coral shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          )}
          <span
            className={`text-2xl sm:text-3xl font-serif font-bold ${
              summary.overdue > 0 ? 'text-coral' : 'text-ink'
            }`}
          >
            {summary.overdue}
          </span>
        </div>
        <span className="text-muted text-xs mt-1">Requires immediate attention</span>
      </div>

      {/* 4. SLA Met */}
      <div className="bg-paper border border-line rounded-lg p-4 shadow-sm flex flex-col justify-between">
        <span className="text-muted text-xs uppercase tracking-wider font-medium">
          SLA met
        </span>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-serif font-bold text-ink">
            {summary.slaMetPercent}
          </span>
        </div>
        <span className="text-muted text-xs mt-1">{summary.slaMetRatio}</span>
      </div>
    </div>
  );
};

