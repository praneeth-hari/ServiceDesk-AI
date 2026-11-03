import React from 'react';
import { getFriendlyErrorMessage } from '../../../utils/errors';

export interface ReportCardProps {
  title: string;
  subtitle?: string;
  headerRight?: React.ReactNode;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: boolean;
  emptyMessage?: string;
  viewMode?: 'chart' | 'table';
  onViewModeChange?: (mode: 'chart' | 'table') => void;
  hasTableView?: boolean;
  children: React.ReactNode;
  className?: string;
}

export const ReportCard: React.FC<ReportCardProps> = ({
  title,
  subtitle,
  headerRight,
  loading = false,
  error = null,
  onRetry,
  empty = false,
  emptyMessage = 'No tickets yet',
  viewMode = 'chart',
  onViewModeChange,
  hasTableView = false,
  children,
  className = '',
}) => {
  return (
    <div
      className={`bg-paper border border-line rounded-lg p-5 flex flex-col justify-between shadow-sm ${className}`}
    >
      {/* Card Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-line gap-2">
        <div>
          <h2 className="font-serif text-lg font-semibold text-ink">{title}</h2>
          {subtitle && <p className="text-muted text-xs mt-0.5">{subtitle}</p>}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {headerRight}

          {hasTableView && onViewModeChange && !loading && !error && (
            <button
              type="button"
              onClick={() => onViewModeChange(viewMode === 'chart' ? 'table' : 'chart')}
              className="text-xs px-2.5 py-1 rounded border border-line bg-paper2/60 text-ink hover:bg-paper2 hover:text-teal font-medium transition-colors"
              aria-label={viewMode === 'chart' ? `View ${title} as table` : `View ${title} as chart`}
            >
              {viewMode === 'chart' ? 'View as table' : 'View as chart'}
            </button>
          )}
        </div>
      </div>

      {/* Card Body */}
      <div className="pt-4 flex-1">
        {loading ? (
          <div className="space-y-3 py-4 animate-pulse">
            <div className="h-6 bg-paper2 rounded w-1/3" />
            <div className="h-32 bg-paper2 rounded w-full" />
            <div className="h-4 bg-paper2 rounded w-1/2" />
          </div>
        ) : error ? (
          <div className="py-8 px-4 text-center rounded bg-paper2/50 border border-line flex flex-col items-center justify-center">
            <p className="text-xs sm:text-sm text-muted mb-3 font-medium">
              {getFriendlyErrorMessage(error, 'A server problem occurred. Please try again.')}
            </p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="px-3 py-1.5 rounded bg-teal text-paper text-xs font-medium hover:bg-teal/90 transition-colors"
              >
                Retry
              </button>
            )}
          </div>
        ) : empty ? (
          <div className="py-12 text-center text-muted text-sm font-medium">
            {emptyMessage}
          </div>
        ) : (
          <div className="w-full">{children}</div>
        )}
      </div>
    </div>
  );
};

