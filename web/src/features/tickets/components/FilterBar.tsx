import React from 'react';

export interface FilterState {
  status: string;
  priority: string;
  assigneeId: string;
  q: string;
  view: 'timeline' | 'table';
}

interface AssigneeOption {
  id: number;
  name: string;
}

interface FilterBarProps {
  filters: FilterState;
  onFilterChange: (newFilters: Partial<FilterState>) => void;
  isStaff: boolean;
  assigneeOptions?: AssigneeOption[];
}

export const FilterBar: React.FC<FilterBarProps> = ({
  filters,
  onFilterChange,
  isStaff,
  assigneeOptions = [],
}) => {
  return (
    <div className="bg-paper2 border border-line rounded-lg p-3 sm:p-4 mb-6 flex flex-wrap items-center justify-between gap-3">
      {/* Left side: filter controls */}
      <div className="flex flex-wrap items-center gap-2.5 sm:gap-3 flex-1 min-w-[280px]">
        {/* Search */}
        <div className="relative min-w-[180px] sm:min-w-[220px] flex-1 sm:flex-initial">
          <input
            type="text"
            value={filters.q}
            onChange={(e) => onFilterChange({ q: e.target.value })}
            placeholder="Search tickets by title..."
            className="w-full bg-paper border border-line rounded px-3 py-1.5 text-xs sm:text-sm text-ink placeholder-muted focus:outline-none focus:border-teal"
            aria-label="Search tickets by title"
          />
          {filters.q && (
            <button
              type="button"
              onClick={() => onFilterChange({ q: '' })}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-ink text-xs px-1"
              aria-label="Clear search"
            >
              ×
            </button>
          )}
        </div>

        {/* Status Dropdown */}
        <div className="flex items-center">
          <label htmlFor="filter-status" className="sr-only">
            Status
          </label>
          <select
            id="filter-status"
            value={filters.status}
            onChange={(e) => onFilterChange({ status: e.target.value })}
            className="bg-paper border border-line rounded px-2.5 py-1.5 text-xs sm:text-sm text-ink focus:outline-none focus:border-teal"
            aria-label="Filter by status"
          >
            <option value="">All Statuses</option>
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="waiting_on_requester">Waiting on Requester</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        {/* Priority Dropdown */}
        <div className="flex items-center">
          <label htmlFor="filter-priority" className="sr-only">
            Priority
          </label>
          <select
            id="filter-priority"
            value={filters.priority}
            onChange={(e) => onFilterChange({ priority: e.target.value })}
            className="bg-paper border border-line rounded px-2.5 py-1.5 text-xs sm:text-sm text-ink focus:outline-none focus:border-teal"
            aria-label="Filter by priority"
          >
            <option value="">All Priorities</option>
            <option value="urgent">Urgent</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        {/* Assignee Dropdown (Staff only) */}
        {isStaff && (
          <div className="flex items-center">
            <label htmlFor="filter-assignee" className="sr-only">
              Assignee
            </label>
            <select
              id="filter-assignee"
              value={filters.assigneeId}
              onChange={(e) => onFilterChange({ assigneeId: e.target.value })}
              className="bg-paper border border-line rounded px-2.5 py-1.5 text-xs sm:text-sm text-ink focus:outline-none focus:border-teal max-w-[160px] truncate"
              aria-label="Filter by assignee"
            >
              <option value="">All Assignees</option>
              {assigneeOptions.map((opt) => (
                <option key={opt.id} value={opt.id.toString()}>
                  {opt.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Right side: View Toggle */}
      <div className="flex items-center border border-line rounded p-0.5 bg-paper self-end sm:self-center">
        <button
          type="button"
          onClick={() => onFilterChange({ view: 'timeline' })}
          className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
            filters.view === 'timeline'
              ? 'bg-paper2 text-teal font-semibold shadow-xs'
              : 'text-muted hover:text-ink'
          }`}
          aria-pressed={filters.view === 'timeline'}
          aria-label="Timeline view"
        >
          Timeline
        </button>
        <button
          type="button"
          onClick={() => onFilterChange({ view: 'table' })}
          className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
            filters.view === 'table'
              ? 'bg-paper2 text-teal font-semibold shadow-xs'
              : 'text-muted hover:text-ink'
          }`}
          aria-pressed={filters.view === 'table'}
          aria-label="Table view"
        >
          Table
        </button>
      </div>
    </div>
  );
};
