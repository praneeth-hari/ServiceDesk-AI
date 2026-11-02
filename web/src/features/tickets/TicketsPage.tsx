import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '../../context/useAuth';
import { listTickets } from '../../api/tickets';
import type { Ticket, TicketStatus, TicketPriority } from '../../api/types';
import { FilterBar, type FilterState } from './components/FilterBar';
import { TimelineView } from './components/TimelineView';
import { TableView } from './components/TableView';
import { classifyTicketSla } from './slaState';

export const TicketsPage: React.FC = () => {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const isStaff = user?.role === 'agent' || user?.role === 'admin';

  // Read URL params
  const viewParam = (searchParams.get('view') as 'timeline' | 'table') || 'timeline';
  const statusParam = searchParams.get('status') || '';
  const priorityParam = searchParams.get('priority') || '';
  const assigneeIdParam = searchParams.get('assignee_id') || '';
  const qParam = searchParams.get('q') || '';
  const pageParam = parseInt(searchParams.get('page') || '1', 10);
  const sortByParam = searchParams.get('sort_by') || 'due_at';
  const sortOrderParam = (searchParams.get('order') as 'asc' | 'desc') || 'asc';

  // State
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Filter state for the FilterBar
  const filters: FilterState = useMemo(
    () => ({
      status: statusParam,
      priority: priorityParam,
      assigneeId: assigneeIdParam,
      q: qParam,
      view: viewParam,
    }),
    [statusParam, priorityParam, assigneeIdParam, qParam, viewParam]
  );

  // Update URL params helper
  const updateUrlParams = useCallback(
    (updates: Record<string, string | null | undefined>) => {
      const next = new URLSearchParams(searchParams);
      for (const [key, value] of Object.entries(updates)) {
        if (value === null || value === undefined || value === '') {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const handleFilterChange = (newFilters: Partial<FilterState>) => {
    const updates: Record<string, string | null | undefined> = {};
    if (newFilters.view !== undefined) updates.view = newFilters.view;
    if (newFilters.status !== undefined) {
      updates.status = newFilters.status;
      updates.page = '1';
    }
    if (newFilters.priority !== undefined) {
      updates.priority = newFilters.priority;
      updates.page = '1';
    }
    if (newFilters.assigneeId !== undefined) {
      updates.assignee_id = newFilters.assigneeId;
      updates.page = '1';
    }
    if (newFilters.q !== undefined) {
      updates.q = newFilters.q;
      updates.page = '1';
    }
    updateUrlParams(updates);
  };

  const handleSortChange = (newSortBy: string) => {
    if (sortByParam === newSortBy) {
      updateUrlParams({
        order: sortOrderParam === 'asc' ? 'desc' : 'asc',
      });
    } else {
      updateUrlParams({
        sort_by: newSortBy,
        order: 'asc',
      });
    }
  };

  const handlePageChange = (newPage: number) => {
    updateUrlParams({ page: newPage.toString() });
  };

  // Fetch tickets on params/reloadKey change
  useEffect(() => {
    let ignore = false;

    const load = async () => {
      try {
        const backendSortBy = sortByParam === 'id' ? 'created_at' : sortByParam;
        const res = await listTickets({
          page: pageParam,
          page_size: pageSize,
          status: (statusParam as TicketStatus) || undefined,
          priority: (priorityParam as TicketPriority) || undefined,
          assignee_id: assigneeIdParam ? parseInt(assigneeIdParam, 10) : undefined,
          q: qParam || undefined,
          sort_by: backendSortBy as 'created_at' | 'updated_at' | 'due_at',
          order: sortOrderParam,
        });

        if (!ignore) {
          let items = res.items;
          if (sortByParam === 'id') {
            items = [...items].sort((a, b) =>
              sortOrderParam === 'asc' ? a.id - b.id : b.id - a.id
            );
          }
          setTickets(items);
          setTotal(res.total);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load tickets');
          setLoading(false);
        }
      }
    };

    load();

    return () => {
      ignore = true;
    };
  }, [pageParam, pageSize, statusParam, priorityParam, assigneeIdParam, qParam, sortByParam, sortOrderParam, reloadKey]);

  // Compute summary metrics from current loaded tickets
  const summary = useMemo(() => {
    let breached = 0;
    let atRisk = 0;
    let paused = 0;

    for (const t of tickets) {
      const sla = classifyTicketSla(t);
      if (sla.category === 'breached') breached++;
      else if (sla.category === 'atRisk') atRisk++;
      else if (sla.category === 'paused') paused++;
    }

    return {
      shown: tickets.length,
      breached,
      atRisk,
      paused,
    };
  }, [tickets]);

  // Derive distinct assignees from loaded tickets
  const assigneeOptions = useMemo(() => {
    const map = new Map<number, string>();
    for (const t of tickets) {
      if (t.assignee_id && t.assignee_name) {
        map.set(t.assignee_id, t.assignee_name);
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [tickets]);

  return (
    <div className="space-y-6">
      {/* Page Title & Summary Header */}
      <div className="border-b border-line pb-4 flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
        <div>
          <h1 className="font-serif text-3xl font-semibold text-ink">Tickets</h1>
          <p className="text-muted text-xs sm:text-sm mt-1">
            Showing <span className="font-semibold text-ink">{summary.shown}</span> tickets
            {' · '}
            <span className="font-semibold text-coral">{summary.breached} breached</span>
            {' · '}
            <span className="font-semibold text-amber">{summary.atRisk} at risk</span>
            {' · '}
            <span className="font-semibold text-purple">{summary.paused} paused</span>
          </p>
        </div>
        <div>
          <Link
            to="/tickets/new"
            className="inline-flex items-center px-3 py-1.5 rounded bg-teal text-paper text-xs sm:text-sm font-medium hover:bg-teal/90 transition-colors"
          >
            + New Ticket
          </Link>
        </div>
      </div>

      {/* Filter Row */}
      <FilterBar
        filters={filters}
        onFilterChange={handleFilterChange}
        isStaff={isStaff}
        assigneeOptions={assigneeOptions}
      />

      {/* Main Content Area: Loading / Error / Empty / Views */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="h-12 bg-paper2/70 border border-line rounded-lg animate-pulse"
            />
          ))}
        </div>
      ) : error ? (
        <div className="bg-coral/10 border border-coral/40 rounded-lg p-6 text-center max-w-xl mx-auto">
          <h2 className="font-serif text-lg font-semibold text-coral mb-2">Unable to Load Tickets</h2>
          <p className="text-xs sm:text-sm text-ink mb-4">{error}</p>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              setReloadKey((k) => k + 1);
            }}
            className="px-4 py-1.5 rounded bg-teal text-paper text-xs sm:text-sm font-medium hover:bg-teal/90 transition-colors"
          >
            Retry
          </button>
        </div>
      ) : tickets.length === 0 ? (
        <div className="bg-paper2 border border-line rounded-lg p-8 sm:p-12 text-center max-w-lg mx-auto">
          <h2 className="font-serif text-2xl font-semibold text-ink mb-2">No Tickets Found</h2>
          <p className="text-xs sm:text-sm text-muted mb-6">
            There are no tickets matching your current search or filter criteria.
          </p>
          <div className="flex items-center justify-center gap-3">
            {(filters.status || filters.priority || filters.assigneeId || filters.q) && (
              <button
                type="button"
                onClick={() =>
                  handleFilterChange({
                    status: '',
                    priority: '',
                    assigneeId: '',
                    q: '',
                  })
                }
                className="px-3 py-1.5 rounded bg-paper border border-line text-ink text-xs sm:text-sm hover:border-teal transition-colors"
              >
                Clear Filters
              </button>
            )}
            <Link
              to="/tickets/new"
              className="px-4 py-1.5 rounded bg-teal text-paper text-xs sm:text-sm font-medium hover:bg-teal/90 transition-colors"
            >
              Create New Ticket
            </Link>
          </div>
        </div>
      ) : viewParam === 'table' ? (
        <TableView
          tickets={tickets}
          isStaff={isStaff}
          total={total}
          page={pageParam}
          pageSize={pageSize}
          sortBy={sortByParam}
          sortOrder={sortOrderParam}
          onSortChange={handleSortChange}
          onPageChange={handlePageChange}
        />
      ) : (
        <TimelineView tickets={tickets} isStaff={isStaff} />
      )}
    </div>
  );
};
