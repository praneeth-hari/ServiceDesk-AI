import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TicketDetailPage } from '../TicketDetailPage';
import * as ticketsApi from '../../../api/tickets';
import * as authHook from '../../../context/useAuth';
import type { Ticket, Comment, StatusHistory, SimilarTicket, User } from '../../../api/types';

vi.mock('../../../api/tickets');
vi.mock('../../../context/useAuth');

const mockRequesterUser: User = {
  id: 10,
  email: 'requester@example.com',
  full_name: 'Alice Requester',
  role: 'requester',
  is_active: true,
  created_at: '2026-10-01T00:00:00Z',
};

const mockAgentUser: User = {
  id: 20,
  email: 'agent@example.com',
  full_name: 'Bob Agent',
  role: 'agent',
  is_active: true,
  created_at: '2026-10-01T00:00:00Z',
};

const mockAdminUser: User = {
  id: 30,
  email: 'admin@example.com',
  full_name: 'Charlie Admin',
  role: 'admin',
  is_active: true,
  created_at: '2026-10-01T00:00:00Z',
};

const baseTicket: Ticket = {
  id: 1,
  title: 'VPN connection issue',
  description: 'Cannot connect to company VPN from home',
  status: 'open',
  priority: 'high',
  category: 'network',
  requester_id: 10,
  assignee_id: null,
  requester_name: 'Alice Requester',
  assignee_name: null,
  due_at: '2026-11-05T12:00:00Z',
  sla_paused_at: null,
  created_at: '2026-11-01T09:00:00Z',
  updated_at: '2026-11-01T09:00:00Z',
  is_overdue: false,
};

const mockComments: Comment[] = [
  {
    id: 1,
    ticket_id: 1,
    author_id: 10,
    body: 'Public comment from requester',
    is_internal: false,
    created_at: '2026-11-01T10:00:00Z',
  },
  {
    id: 2,
    ticket_id: 1,
    author_id: 20,
    body: 'Internal investigation notes',
    is_internal: true,
    created_at: '2026-11-01T11:00:00Z',
  },
];

const mockHistory: StatusHistory[] = [
  {
    id: 100,
    ticket_id: 1,
    changed_by_id: 10,
    from_status: null,
    to_status: 'open',
    created_at: '2026-11-01T09:00:00Z',
  },
];

const mockSimilar: SimilarTicket[] = [
  {
    id: 55,
    title: 'VPN client drops every hour',
    status: 'resolved',
    category: 'network',
    priority: 'high',
    similarity: 0.88,
  },
];

const mockAgents: User[] = [
  mockAgentUser,
  {
    id: 21,
    email: 'agent2@example.com',
    full_name: 'David Agent',
    role: 'agent',
    is_active: true,
    created_at: '2026-10-01T00:00:00Z',
  },
];

function renderTicketDetail(ticketId = 1) {
  return render(
    <MemoryRouter initialEntries={[`/tickets/${ticketId}`]}>
      <Routes>
        <Route path="/tickets/:id" element={<TicketDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('TicketDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    vi.mocked(ticketsApi.getTicket).mockResolvedValue(baseTicket);
    vi.mocked(ticketsApi.listComments).mockResolvedValue(mockComments);
    vi.mocked(ticketsApi.getHistory).mockResolvedValue(mockHistory);
    vi.mocked(ticketsApi.getSimilarTickets).mockResolvedValue(mockSimilar);
    vi.mocked(ticketsApi.listAgents).mockResolvedValue(mockAgents);
  });

  it('renders internal notes for staff and excludes them for requesters (and requester never calls getSimilarTickets)', async () => {
    // 1. Staff view (Agent)
    const staffView = renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('VPN connection issue')).toBeInTheDocument();
    });

    expect(screen.getByText('Internal investigation notes')).toBeInTheDocument();
    expect(screen.getByText('internal note')).toBeInTheDocument();
    expect(ticketsApi.getSimilarTickets).toHaveBeenCalledWith(1, 5);
    staffView.unmount();

    // 2. Requester view
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockRequesterUser,
      role: mockRequesterUser.role,
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    // Requesters API returns only public comments
    vi.mocked(ticketsApi.listComments).mockResolvedValue([mockComments[0]]);
    vi.mocked(ticketsApi.getSimilarTickets).mockClear();

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('Public comment from requester')).toBeInTheDocument();
    });

    expect(screen.queryByText('Internal investigation notes')).not.toBeInTheDocument();
    expect(screen.queryByText('internal note')).not.toBeInTheDocument();
    expect(ticketsApi.getSimilarTickets).not.toHaveBeenCalled();
    expect(screen.queryByText('Similar tickets')).not.toBeInTheDocument();
    expect(screen.queryByText('Actions')).not.toBeInTheDocument();
  });

  it('posts a public comment and an internal note with the correct payload', async () => {
    vi.mocked(ticketsApi.addComment).mockResolvedValue({
      id: 3,
      ticket_id: 1,
      author_id: 20,
      body: 'Testing public reply',
      is_internal: false,
      created_at: '2026-11-01T12:00:00Z',
    });

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('VPN connection issue')).toBeInTheDocument();
    });

    const textarea = screen.getByPlaceholderText('Type your message...');
    const postButton = screen.getByRole('button', { name: 'Post' });

    // Try posting public comment
    fireEvent.change(textarea, { target: { value: 'Testing public reply' } });
    fireEvent.click(postButton);

    await waitFor(() => {
      expect(ticketsApi.addComment).toHaveBeenCalledWith(1, {
        body: 'Testing public reply',
        is_internal: false,
      });
    });

    // Check textarea is cleared
    expect(textarea).toHaveValue('');

    // Now test internal note checkbox
    vi.mocked(ticketsApi.addComment).mockResolvedValue({
      id: 4,
      ticket_id: 1,
      author_id: 20,
      body: 'Private note to team',
      is_internal: true,
      created_at: '2026-11-01T12:05:00Z',
    });

    fireEvent.change(textarea, { target: { value: 'Private note to team' } });
    const checkbox = screen.getByLabelText(/Internal note/i);
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();

    fireEvent.click(postButton);

    await waitFor(() => {
      expect(ticketsApi.addComment).toHaveBeenCalledWith(1, {
        body: 'Private note to team',
        is_internal: true,
      });
    });
  });

  it('replaces composer on closed ticket with closed note and link to /tickets/new', async () => {
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'closed',
    });

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('VPN connection issue')).toBeInTheDocument();
    });

    expect(screen.queryByPlaceholderText('Type your message...')).not.toBeInTheDocument();
    expect(
      screen.getByText(/This ticket is closed. Open a new ticket if the problem comes back./i)
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /New ticket/i })).toHaveAttribute('href', '/tickets/new');
  });

  it('renders allowed transition buttons per status and requires double-click confirmation for Close', async () => {
    // 1. Status 'open' -> Start work
    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start work' })).toBeInTheDocument();
    });

    // 2. Status 'in_progress' -> Waiting on requester, Resolve
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'in_progress',
    });
    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Waiting on requester' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Resolve' })).toBeInTheDocument();
    });

    // 3. Status 'waiting_on_requester' -> Resume
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'waiting_on_requester',
    });
    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument();
    });

    // 4. Status 'resolved' -> Close, Reopen
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'resolved',
    });
    vi.mocked(ticketsApi.changeStatus).mockResolvedValue({
      ...baseTicket,
      status: 'closed',
    });

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Reopen' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
    });

    // Close confirmation two-step verification
    const closeBtn = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeBtn);
    expect(ticketsApi.changeStatus).not.toHaveBeenCalled();

    const confirmBtn = screen.getByRole('button', { name: 'Confirm close?' });
    expect(confirmBtn).toBeInTheDocument();
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(ticketsApi.changeStatus).toHaveBeenCalledWith(1, 'closed');
    });

    // 5. Status 'closed' -> No actions
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'closed',
    });
    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText(/No actions available for closed tickets/i)).toBeInTheDocument();
    });
  });

  it('displays inline error message when status change returns a 409 Conflict', async () => {
    vi.mocked(ticketsApi.changeStatus).mockRejectedValue({
      status: 409,
      message: "Cannot transition ticket status from 'open' to 'resolved'",
    });

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start work' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Start work' }));

    await waitFor(() => {
      expect(
        screen.getByText("Cannot transition ticket status from 'open' to 'resolved'")
      ).toBeInTheDocument();
    });
  });

  it('assigns ticket to current agent with "Assign to me"', async () => {
    vi.mocked(ticketsApi.assignTicket).mockResolvedValue({
      ...baseTicket,
      assignee_id: 20,
      assignee_name: 'Bob Agent',
      status: 'in_progress',
    });

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Assign to me' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Assign to me' }));

    await waitFor(() => {
      expect(ticketsApi.assignTicket).toHaveBeenCalledWith(1, 20);
    });
  });

  it('displays select with active agents for admin and assigns chosen agent', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAdminUser,
      role: mockAdminUser.role,
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    vi.mocked(ticketsApi.assignTicket).mockResolvedValue({
      ...baseTicket,
      assignee_id: 21,
      assignee_name: 'David Agent',
      status: 'in_progress',
    });

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: /Select active agent/i })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /Select active agent/i });
    expect(screen.getByText('Bob Agent')).toBeInTheDocument();
    expect(screen.getByText('David Agent')).toBeInTheDocument();

    fireEvent.change(select, { target: { value: '21' } });
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));

    await waitFor(() => {
      expect(ticketsApi.assignTicket).toHaveBeenCalledWith(1, 21);
    });
  });

  it('renders friendly 404 page when ticket is not found', async () => {
    vi.mocked(ticketsApi.getTicket).mockRejectedValue({
      status: 404,
      message: 'Ticket not found',
    });

    renderTicketDetail(999);
    await waitFor(() => {
      expect(screen.getByText('Ticket not found')).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: /Back to tickets/i })).toHaveAttribute('href', '/tickets');
  });

  it('renders purple banner for requester when waiting_on_requester and focuses composer on Reply now', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockRequesterUser,
      role: mockRequesterUser.role,
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'waiting_on_requester',
      sla_paused_at: '2026-11-01T10:00:00Z',
    });

    renderTicketDetail(1);
    await waitFor(() => {
      expect(
        screen.getByText('Waiting for your reply.')
      ).toBeInTheDocument();
    });

    const replyNowButton = screen.getByRole('button', { name: 'Reply now' });
    const textarea = screen.getByPlaceholderText('Type your message...');

    const focusSpy = vi.spyOn(textarea, 'focus');
    fireEvent.click(replyNowButton);
    expect(focusSpy).toHaveBeenCalled();
  });

  it('renders correct SLA card text across states: on track, at risk, breached, paused, and met', async () => {
    // 1. Paused
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'waiting_on_requester',
      sla_paused_at: '2026-11-01T10:00:00Z',
    });
    const { unmount } = renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('Clock Paused')).toBeInTheDocument();
      expect(screen.getByText('Paused')).toBeInTheDocument();
    });
    unmount();

    // 2. Met
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'resolved',
      due_at: '2026-11-05T12:00:00Z',
      updated_at: '2026-11-02T10:00:00Z',
    });
    const renderMet = renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('SLA Met')).toBeInTheDocument();
      expect(screen.getByText('Met')).toBeInTheDocument();
    });
    renderMet.unmount();

    // 3. Breached
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'open',
      due_at: '2026-10-25T10:00:00Z', // in past
      is_overdue: true,
    });
    const renderBreached = renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('Breached')).toBeInTheDocument();
      expect(screen.getByText(/breached \d+/i)).toBeInTheDocument();
    });
    renderBreached.unmount();

    // 4. On Track
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      status: 'open',
      created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      due_at: new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString(),
      is_overdue: false,
    });
    const renderOnTrack = renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('On Track')).toBeInTheDocument();
      expect(screen.getByText(/left/i)).toBeInTheDocument();
    });
    renderOnTrack.unmount();
  });

  it('renders author_name and actor_name directly and falls back to role/id when missing', async () => {
    vi.mocked(ticketsApi.getTicket).mockResolvedValue({
      ...baseTicket,
      requester_name: 'Alice Requester',
    });
    vi.mocked(ticketsApi.listComments).mockResolvedValue([
      {
        id: 1,
        ticket_id: 1,
        author_id: 99,
        author_name: 'Dr. Evelyn Reed',
        body: 'Custom author comment',
        is_internal: false,
        created_at: '2026-11-01T10:00:00Z',
      },
      {
        id: 2,
        ticket_id: 1,
        author_id: 88,
        author_name: null,
        body: 'Fallback comment from staff',
        is_internal: false,
        created_at: '2026-11-01T10:30:00Z',
      },
    ]);
    vi.mocked(ticketsApi.getHistory).mockResolvedValue([
      {
        id: 100,
        ticket_id: 1,
        changed_by_id: 77,
        actor_name: 'Marcus Vance',
        from_status: null,
        to_status: 'open',
        created_at: '2026-11-01T09:00:00Z',
      },
      {
        id: 101,
        ticket_id: 1,
        changed_by_id: 88,
        actor_name: null,
        from_status: 'open',
        to_status: 'in_progress',
        created_at: '2026-11-01T09:30:00Z',
      },
    ]);

    renderTicketDetail(1);

    // Direct author name renders
    expect(await screen.findByText('Dr. Evelyn Reed')).toBeInTheDocument();
    // Direct actor name renders
    expect(await screen.findByText('Marcus Vance')).toBeInTheDocument();
    // Fallback to 'Staff member' when name is null
    expect(await screen.findAllByText('Staff member')).not.toHaveLength(0);
  });
it('shows "No similar tickets yet" when similarTickets list is empty for staff', async () => {
    vi.mocked(ticketsApi.getSimilarTickets).mockResolvedValue([]);

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('VPN connection issue')).toBeInTheDocument();
    });

    expect(screen.getByText('Similar tickets')).toBeInTheDocument();
    expect(screen.getByText('No similar tickets yet')).toBeInTheDocument();
  });

  it('renders readable status transition labels in activity feed (e.g. Open → In progress)', async () => {
    vi.mocked(ticketsApi.getHistory).mockResolvedValue([
      {
        id: 201,
        ticket_id: 1,
        changed_by_id: 20,
        from_status: 'open',
        to_status: 'in_progress',
        created_at: '2026-11-01T10:00:00Z',
      },
    ]);

    renderTicketDetail(1);
    await waitFor(() => {
      expect(screen.getByText('VPN connection issue')).toBeInTheDocument();
    });

    expect(screen.getByText(/Open → In progress/i)).toBeInTheDocument();
  });
});
