import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { TicketsPage } from '../TicketsPage';
import * as ticketsApi from '../../../api/tickets';
import * as authHook from '../../../context/useAuth';
import type { PaginatedTickets, Ticket } from '../../../api/types';

vi.mock('../../../context/useAuth');
vi.mock('../../../api/tickets');

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const sampleTickets: Ticket[] = [
  {
    id: 101,
    title: 'VPN Connection Issues',
    description: 'Unable to connect to company VPN from home',
    status: 'open',
    priority: 'high',
    category: 'network',
    requester_id: 1,
    assignee_id: 2,
    requester_name: 'Alice Requester',
    assignee_name: 'Bob Agent',
    created_at: new Date(Date.now() - 3600 * 1000).toISOString(),
    due_at: new Date(Date.now() + 7200 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 3600 * 1000).toISOString(),
    sla_paused_at: null,
    is_overdue: false,
  },
  {
    id: 102,
    title: 'Monitor flickering',
    description: 'Secondary display flickers intermittently',
    status: 'waiting_on_requester',
    priority: 'medium',
    category: 'hardware',
    requester_id: 1,
    assignee_id: 2,
    requester_name: 'Alice Requester',
    assignee_name: 'Bob Agent',
    created_at: new Date(Date.now() - 7200 * 1000).toISOString(),
    due_at: new Date(Date.now() + 14400 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 1800 * 1000).toISOString(),
    sla_paused_at: new Date(Date.now() - 1800 * 1000).toISOString(),
    is_overdue: false,
  },
];

const mockPaginatedResponse: PaginatedTickets = {
  items: sampleTickets,
  total: 2,
  page: 1,
  page_size: 20,
};

describe('TicketsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(authHook.useAuth).mockReturnValue({
      user: {
        id: 2,
        email: 'agent@example.com',
        full_name: 'Bob Agent',
        role: 'agent',
        is_active: true,
        created_at: new Date().toISOString(),
      },
      role: 'agent',
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(ticketsApi.listTickets).mockResolvedValue(mockPaginatedResponse);
  });

  it('renders page header and summary counts', async () => {
    render(
      <MemoryRouter initialEntries={['/tickets']}>
        <TicketsPage />
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { level: 1, name: /tickets/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/showing/i)).toBeInTheDocument();
      expect(screen.getByText(/1 paused/i)).toBeInTheDocument();
    });
  });

  it('renders status pill with Runway design', async () => {
    render(
      <MemoryRouter initialEntries={['/tickets']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      const openPill = screen.getByTestId('status-pill-open');
      expect(openPill).toBeInTheDocument();
      expect(openPill).toHaveTextContent('Open');

      const waitingPill = screen.getByTestId('status-pill-waiting_on_requester');
      expect(waitingPill).toBeInTheDocument();
      expect(waitingPill).toHaveTextContent('Waiting');
    });
  });

  it('draws a bar from the left edge when a ticket starts before the window', async () => {
    // Ticket created 10 days ago, due 1 day in the future
    const clipTicket: Ticket = {
      id: 103,
      title: 'Long running ticket',
      description: 'Started before current window',
      status: 'open',
      priority: 'high',
      category: 'software',
      requester_id: 1,
      assignee_id: 2,
      requester_name: 'Alice Requester',
      assignee_name: 'Bob Agent',
      created_at: new Date(Date.now() - 10 * 24 * 3600 * 1000).toISOString(),
      due_at: new Date(Date.now() + 24 * 3600 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 10 * 24 * 3600 * 1000).toISOString(),
      sla_paused_at: null,
      is_overdue: false,
    };

    vi.mocked(ticketsApi.listTickets).mockResolvedValue({
      items: [clipTicket],
      total: 1,
      page: 1,
      page_size: 20,
    });

    render(
      <MemoryRouter initialEntries={['/tickets?view=timeline']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('clip-left-marker')).toBeInTheDocument();
      const elapsedBar = screen.getByTestId('elapsed-bar');
      expect(elapsedBar).toBeInTheDocument();
      // LABEL_WIDTH = 280, so bar starts at left edge of chart (280)
      expect(elapsedBar.getAttribute('x')).toBe('280');
    });
  });

  it('draws the overdue stretch up to NOW when an open ticket has due before the window', async () => {
    // Ticket created 10 days ago, due 6 days ago (both before window), still open
    const overdueTicket: Ticket = {
      id: 104,
      title: 'Old overdue ticket',
      description: 'Breached before window start',
      status: 'open',
      priority: 'urgent',
      category: 'access',
      requester_id: 1,
      assignee_id: 2,
      requester_name: 'Alice Requester',
      assignee_name: 'Bob Agent',
      created_at: new Date(Date.now() - 10 * 24 * 3600 * 1000).toISOString(),
      due_at: new Date(Date.now() - 6 * 24 * 3600 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 10 * 24 * 3600 * 1000).toISOString(),
      sla_paused_at: null,
      is_overdue: true,
    };

    vi.mocked(ticketsApi.listTickets).mockResolvedValue({
      items: [overdueTicket],
      total: 1,
      page: 1,
      page_size: 20,
    });

    render(
      <MemoryRouter initialEntries={['/tickets?view=timeline']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('clip-left-marker')).toBeInTheDocument();
      const overdueStretch = screen.getByTestId('overdue-stretch');
      expect(overdueStretch).toBeInTheDocument();
      // Overdue stretch starts at left edge (280)
      const rects = overdueStretch.querySelectorAll('rect');
      expect(rects[0].getAttribute('x')).toBe('280');
    });
  });

  it('draws no bar for a resolved ticket that ended before the window', async () => {
    // Ticket created 10 days ago, resolved 6 days ago (both before window)
    const oldResolvedTicket: Ticket = {
      id: 105,
      title: 'Archived legacy issue',
      description: 'Completed before window start',
      status: 'resolved',
      priority: 'low',
      category: 'email',
      requester_id: 1,
      assignee_id: 2,
      requester_name: 'Alice Requester',
      assignee_name: 'Bob Agent',
      created_at: new Date(Date.now() - 10 * 24 * 3600 * 1000).toISOString(),
      due_at: new Date(Date.now() - 8 * 24 * 3600 * 1000).toISOString(),
      updated_at: new Date(Date.now() - 6 * 24 * 3600 * 1000).toISOString(),
      sla_paused_at: null,
      is_overdue: false,
    };

    vi.mocked(ticketsApi.listTickets).mockResolvedValue({
      items: [oldResolvedTicket],
      total: 1,
      page: 1,
      page_size: 20,
    });

    render(
      <MemoryRouter initialEntries={['/tickets?view=timeline']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      // Must draw no bar in the chart
      expect(screen.queryByTestId('elapsed-bar')).not.toBeInTheDocument();
      expect(screen.queryByTestId('overdue-stretch')).not.toBeInTheDocument();
      expect(screen.queryByTestId('remaining-bar')).not.toBeInTheDocument();
      // Shows resolved text
      expect(screen.getByText(/resolved /i)).toBeInTheDocument();
    });
  });

  it('renders timeline view by default and can switch to table view', async () => {
    render(
      <MemoryRouter initialEntries={['/tickets']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('img', { name: /ticket sla business-hours timeline/i })).toBeInTheDocument();
    });

    // Click Table view toggle button
    const tableButton = screen.getByRole('button', { name: /table view/i });
    fireEvent.click(tableButton);

    await waitFor(() => {
      expect(screen.getByRole('columnheader', { name: /title/i })).toBeInTheDocument();
      expect(screen.getByRole('columnheader', { name: /status/i })).toBeInTheDocument();
      expect(screen.getByText('VPN Connection Issues')).toBeInTheDocument();
    });
  });

  it('hides assignee filter and assignee column when logged in as requester', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: {
        id: 1,
        email: 'requester@example.com',
        full_name: 'Alice Requester',
        role: 'requester',
        is_active: true,
        created_at: new Date().toISOString(),
      },
      role: 'requester',
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/tickets?view=table']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('VPN Connection Issues')).toBeInTheDocument();
    });

    // Assignee filter dropdown should NOT exist
    expect(screen.queryByLabelText(/filter by assignee/i)).not.toBeInTheDocument();

    // Assignee column header in table should NOT exist
    expect(screen.queryByRole('columnheader', { name: /assignee/i })).not.toBeInTheDocument();
  });

  it('updates filters and triggers fetch when status filter changes', async () => {
    render(
      <MemoryRouter initialEntries={['/tickets']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(ticketsApi.listTickets).toHaveBeenCalled();
    });

    const statusSelect = screen.getByLabelText(/filter by status/i);
    fireEvent.change(statusSelect, { target: { value: 'open' } });

    await waitFor(() => {
      expect(ticketsApi.listTickets).toHaveBeenCalledWith(
        expect.objectContaining({
          status: 'open',
        })
      );
    });
  });

  it('renders error state and retries on button click', async () => {
    vi.mocked(ticketsApi.listTickets).mockRejectedValueOnce(new Error('Network connection failed'));

    render(
      <MemoryRouter initialEntries={['/tickets']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/unable to load tickets/i)).toBeInTheDocument();
      expect(screen.getByText(/network connection failed/i)).toBeInTheDocument();
    });

    // Now mock resolves on retry
    vi.mocked(ticketsApi.listTickets).mockResolvedValueOnce(mockPaginatedResponse);

    const retryButton = screen.getByRole('button', { name: /retry/i });
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText(/showing/i)).toBeInTheDocument();
    });
  });

  it('navigates to ticket detail on enter key or row click in table view', async () => {
    render(
      <MemoryRouter initialEntries={['/tickets?view=table']}>
        <TicketsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('VPN Connection Issues')).toBeInTheDocument();
    });

    const ticketRow = screen.getByRole('link', { name: /open ticket #101/i });
    fireEvent.click(ticketRow);

    expect(mockNavigate).toHaveBeenCalledWith('/tickets/101');

    // Test Enter key
    fireEvent.keyDown(ticketRow, { key: 'Enter' });
    expect(mockNavigate).toHaveBeenCalledWith('/tickets/101');
  });
});
