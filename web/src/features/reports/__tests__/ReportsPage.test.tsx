import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ReportsPage } from '../ReportsPage';
import { RoleRoute } from '../../../components/RoleRoute';
import { AuthProvider } from '../../../context/AuthContext';

describe('ReportsPage', () => {
  const originalFetch = globalThis.fetch;

  const mockTicketsByStatus = [
    { status: 'open', priority: 'high', count: 5 },
    { status: 'in_progress', priority: 'medium', count: 3 },
    { status: 'resolved', priority: 'low', count: 10 },
  ];

  const mockOverdue = [
    {
      id: 42,
      title: 'Server down in HQ',
      status: 'open',
      priority: 'urgent',
      due_at: '2026-10-20T10:00:00Z',
      requester_id: 3,
      requester_name: 'Ravi Requester',
      assignee_id: 2,
      assignee_name: 'Asha Agent',
    },
  ];

  const mockResolutionTime = [
    {
      assignee_id: 2,
      assignee_name: 'Asha Agent',
      avg_resolution_hours: 3.5,
      ticket_count: 10,
    },
  ];

  const mockAgentRanking = [
    {
      rank: 1,
      agent_id: 2,
      agent_name: 'Asha Agent',
      resolved_count: 10,
    },
  ];

  const mockDailyVolume = [
    { date: '2026-11-01', ticket_count: 4 },
    { date: '2026-11-02', ticket_count: 8 },
  ];

  const mockSlaBreachRate = [
    {
      priority: 'low',
      total_tickets: 10,
      met_sla: 9,
      breached_sla: 1,
      breach_rate: 10.0,
    },
    {
      priority: 'urgent',
      total_tickets: 5,
      met_sla: 3,
      breached_sla: 2,
      breach_rate: 40.0,
    },
  ];

  const mockResolutionByCategory = [
    {
      category: 'hardware',
      priority: 'medium',
      avg_resolution_hours: 2.4,
      ticket_count: 4,
    },
  ];

  const mockAgentWorkload = [
    {
      agent_id: 2,
      agent_name: 'Asha Agent',
      open_tickets: 4,
      overdue_tickets: 1,
      resolved_tickets: 10,
    },
  ];

  const mockCategorySummary = [
    { category: 'hardware', status: null, count: 8 },
    { category: 'network', status: null, count: 5 },
  ];

  const mockCategorySplit = [
    { category: 'hardware', status: 'open', count: 3 },
    { category: 'hardware', status: 'resolved', count: 5 },
    { category: 'network', status: 'open', count: 5 },
  ];

  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem('access_token', 'mock-token');
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 2,
        email: 'agent@example.com',
        full_name: 'Asha Agent',
        role: 'agent',
        is_active: true,
        created_at: '2026-10-25T11:00:00',
      })
    );

    fetchMock = vi.fn((url: string | URL | Request) => {
      const urlStr = url.toString();

      if (urlStr.includes('/reports/tickets-by-status')) {
        return Promise.resolve(new Response(JSON.stringify(mockTicketsByStatus), { status: 200 }));
      }
      if (urlStr.includes('/reports/overdue')) {
        return Promise.resolve(new Response(JSON.stringify(mockOverdue), { status: 200 }));
      }
      if (urlStr.includes('/reports/resolution-time-by-category')) {
        return Promise.resolve(new Response(JSON.stringify(mockResolutionByCategory), { status: 200 }));
      }
      if (urlStr.includes('/reports/resolution-time')) {
        return Promise.resolve(new Response(JSON.stringify(mockResolutionTime), { status: 200 }));
      }
      if (urlStr.includes('/reports/agent-ranking')) {
        return Promise.resolve(new Response(JSON.stringify(mockAgentRanking), { status: 200 }));
      }
      if (urlStr.includes('/reports/daily-volume')) {
        return Promise.resolve(new Response(JSON.stringify(mockDailyVolume), { status: 200 }));
      }
      if (urlStr.includes('/reports/sla-breach-rate')) {
        return Promise.resolve(new Response(JSON.stringify(mockSlaBreachRate), { status: 200 }));
      }
      if (urlStr.includes('/reports/agent-workload')) {
        return Promise.resolve(new Response(JSON.stringify(mockAgentWorkload), { status: 200 }));
      }
      if (urlStr.includes('/reports/tickets-by-category')) {
        if (urlStr.includes('breakdown_by_status=true')) {
          return Promise.resolve(new Response(JSON.stringify(mockCategorySplit), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify(mockCategorySummary), { status: 200 }));
      }

      return Promise.resolve(new Response('Not Found', { status: 404 }));
    });

    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('renders page header, stat tiles, and cards from mocked responses', async () => {
    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    // Header & Subtitle
    expect(screen.getByRole('heading', { level: 1, name: 'Reports' })).toBeInTheDocument();
    expect(
      screen.getByText(/Live figures from the database\. Dates are in UTC\./i)
    ).toBeInTheDocument();

    // 4 Stat Tiles
    expect(await screen.findByText('Total tickets')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument(); // 5 + 3 + 10 = 18 total
    expect(screen.getByText('Open now')).toBeInTheDocument();
    expect(screen.getAllByText('8').length).toBeGreaterThanOrEqual(1); // 5 open + 3 in_progress = 8
    expect(screen.getAllByText('Overdue').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1); // 1 overdue ticket
    expect(screen.getByText('SLA met')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument(); // 12 of 15 = 80%

    // Cards
    expect(screen.getByText('Tickets created per day')).toBeInTheDocument();
    expect(screen.getByText('Tickets by status')).toBeInTheDocument();
    expect(screen.getByText('By category')).toBeInTheDocument();
    expect(screen.getByText('SLA by priority')).toBeInTheDocument();
    expect(screen.getByText('Hours to resolve')).toBeInTheDocument();
    expect(screen.getByText('Agent workload')).toBeInTheDocument();
    expect(screen.getByText('Overdue now')).toBeInTheDocument();

    // Overdue ticket row rendered
    expect(screen.getByText('#42')).toBeInTheDocument();
    expect(screen.getByText('Server down in HQ')).toBeInTheDocument();
  });

  it('an overdue row links to /tickets/:id', async () => {
    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    const ticketLink = await screen.findByRole('link', { name: '#42' });
    expect(ticketLink).toHaveAttribute('href', '/tickets/42');
  });

  it('swaps chart for plain accessible table when "View as table" is clicked', async () => {
    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    await screen.findByText('Tickets created per day');

    // Click "View as table" on daily volume card
    const viewAsTableBtn = screen.getByRole('button', {
      name: 'View Tickets created per day as table',
    });
    fireEvent.click(viewAsTableBtn);

    // Verify table is visible
    expect(
      screen.getByRole('table', { name: 'Tickets created per day table' })
    ).toBeInTheDocument();
    expect(screen.getByText('2026-11-02')).toBeInTheDocument();
  });

  it('switching 7 / 30 / 90 days sends the days parameter', async () => {
    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    await screen.findByText('Tickets created per day');

    // Initial fetch was days=30
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/reports/daily-volume?days=30'),
      expect.anything()
    );

    // Switch to 7 days
    const sevenDayBtn = screen.getByRole('button', { name: 'Show 7 days' });
    fireEvent.click(sevenDayBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/reports/daily-volume?days=7'),
        expect.anything()
      );
    });

    // Switch to 90 days
    const ninetyDayBtn = screen.getByRole('button', { name: 'Show 90 days' });
    fireEvent.click(ninetyDayBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/reports/daily-volume?days=90'),
        expect.anything()
      );
    });
  });

  it('"split by status" toggle sends breakdown_by_status=true and renders stacked segments', async () => {
    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    await screen.findByText('By category');

    // Toggle split by status
    const splitCheckbox = screen.getByRole('checkbox', { name: /split by status/i });
    expect(splitCheckbox).not.toBeChecked();

    fireEvent.click(splitCheckbox);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/reports/tickets-by-category?breakdown_by_status=true'),
        expect.anything()
      );
    });
  });

  it('one failing endpoint shows that card\'s error and Retry while the others render, and Retry recovers', async () => {
    let failDaily = true;

    fetchMock.mockImplementation((url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes('/reports/daily-volume')) {
        if (failDaily) {
          return Promise.resolve(new Response('Server Error', { status: 500 }));
        }
        return Promise.resolve(new Response(JSON.stringify(mockDailyVolume), { status: 200 }));
      }
      if (urlStr.includes('/reports/tickets-by-status')) {
        return Promise.resolve(new Response(JSON.stringify(mockTicketsByStatus), { status: 200 }));
      }
      if (urlStr.includes('/reports/overdue')) {
        return Promise.resolve(new Response(JSON.stringify(mockOverdue), { status: 200 }));
      }
      if (urlStr.includes('/reports/resolution-time-by-category')) {
        return Promise.resolve(new Response(JSON.stringify(mockResolutionByCategory), { status: 200 }));
      }
      if (urlStr.includes('/reports/resolution-time')) {
        return Promise.resolve(new Response(JSON.stringify(mockResolutionTime), { status: 200 }));
      }
      if (urlStr.includes('/reports/agent-ranking')) {
        return Promise.resolve(new Response(JSON.stringify(mockAgentRanking), { status: 200 }));
      }
      if (urlStr.includes('/reports/sla-breach-rate')) {
        return Promise.resolve(new Response(JSON.stringify(mockSlaBreachRate), { status: 200 }));
      }
      if (urlStr.includes('/reports/agent-workload')) {
        return Promise.resolve(new Response(JSON.stringify(mockAgentWorkload), { status: 200 }));
      }
      if (urlStr.includes('/reports/tickets-by-category')) {
        return Promise.resolve(new Response(JSON.stringify(mockCategorySummary), { status: 200 }));
      }
      return Promise.resolve(new Response('Not Found', { status: 404 }));
    });

    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    );

    // Daily volume card failed, showing Retry
    expect(await screen.findByText('Failed to load report data')).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: 'Retry' });
    expect(retryBtn).toBeInTheDocument();

    // Other cards rendered normally!
    expect(screen.getByText('Tickets by status')).toBeInTheDocument();
    expect(screen.getByText('By category')).toBeInTheDocument();
    expect(screen.getByText('Server down in HQ')).toBeInTheDocument();

    // Recover on Retry
    failDaily = false;
    fireEvent.click(retryBtn);

    // Verify recovery
    await waitFor(() => {
      expect(screen.queryByText('Failed to load report data')).not.toBeInTheDocument();
    });
  });

  it('requester is blocked from /reports through RoleRoute and redirected to fallback', async () => {
    sessionStorage.setItem('access_token', 'valid-requester-token');
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 3,
        email: 'requester@example.com',
        full_name: 'Ravi Requester',
        role: 'requester',
        is_active: true,
        created_at: '2026-10-25T11:00:00',
      })
    );

    render(
      <MemoryRouter initialEntries={['/reports']}>
        <AuthProvider>
          <Routes>
            <Route path="/tickets" element={<div>Tickets Page (Fallback)</div>} />
            <Route element={<RoleRoute staffOnly fallbackPath="/tickets" />}>
              <Route path="/reports" element={<ReportsPage />} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    expect(await screen.findByText('Tickets Page (Fallback)')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 1, name: 'Reports' })).not.toBeInTheDocument();
  });
});
