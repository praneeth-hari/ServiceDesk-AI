import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AITriageStrip } from '../AITriageStrip';
import * as ticketsApi from '../../../api/tickets';
import * as authHook from '../../../context/useAuth';
import type { Ticket, TriageFeedbackRead, User } from '../../../api/types';

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
  title: 'Cannot access intranet',
  description: 'Network gateway fails to route',
  status: 'open',
  priority: 'low',
  category: 'other',
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

const baseFeedback: TriageFeedbackRead = {
  id: 101,
  ticket_id: 1,
  method: 'knn',
  embedder: 'hashing-v2',
  suggested_category: 'network',
  suggested_priority: 'high',
  requester_category: 'other',
  requester_priority: 'low',
  final_category: null,
  final_priority: null,
  final_set_by: null,
  final_set_at: null,
  created_at: '2026-11-01T09:00:00Z',
};

describe('AITriageStrip', () => {
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

    vi.mocked(ticketsApi.getTicketTriageFeedback).mockResolvedValue(baseFeedback);
    vi.mocked(ticketsApi.confirmTriageFeedback).mockResolvedValue({
      ...baseFeedback,
      final_category: 'network',
      final_priority: 'high',
      final_set_by: 20,
      final_set_at: '2026-11-01T10:00:00Z',
    });
    vi.mocked(ticketsApi.updateTicket).mockResolvedValue({
      ...baseTicket,
      category: 'network',
      priority: 'high',
    });
  });

  it('hidden for requester: when user role is requester, strip renders nothing', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockRequesterUser,
      role: mockRequesterUser.role,
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(<AITriageStrip ticket={baseTicket} />);

    expect(screen.queryByLabelText(/AI Triage Review/i)).not.toBeInTheDocument();
    expect(ticketsApi.getTicketTriageFeedback).not.toHaveBeenCalled();
  });

  it('hidden on 404: when API returns 404, strip renders nothing', async () => {
    vi.mocked(ticketsApi.getTicketTriageFeedback).mockRejectedValue({ status: 404 });

    render(<AITriageStrip ticket={baseTicket} />);

    await waitFor(() => {
      expect(ticketsApi.getTicketTriageFeedback).toHaveBeenCalledWith(1);
    });

    expect(screen.queryByLabelText(/AI Triage Review/i)).not.toBeInTheDocument();
  });

  it('renders three columns: shows AI suggested, Requester chose, Current ticket columns', async () => {
    render(<AITriageStrip ticket={baseTicket} />);

    await waitFor(() => {
      expect(screen.getByText('AI Triage')).toBeInTheDocument();
    });

    // Method badge
    expect(screen.getByText('kNN')).toBeInTheDocument();

    // 3 column headings
    expect(screen.getByText('AI suggested')).toBeInTheDocument();
    expect(screen.getByText('Requester chose')).toBeInTheDocument();
    expect(screen.getByText('Current ticket')).toBeInTheDocument();

    // Content in columns
    expect(screen.getByText('network')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();

    // Status: awaiting review
    expect(screen.getByText('Awaiting your review')).toBeInTheDocument();

    // Agent sees priority changes notice
    expect(screen.getByText('Priority changes need an admin')).toBeInTheDocument();

    // Buttons
    expect(screen.getByRole('button', { name: 'Apply AI suggestion' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark reviewed as is' })).toBeInTheDocument();
  });

  it('Apply agent category only: agent clicking Apply calls PATCH with category only (not priority)', async () => {
    const onTicketUpdated = vi.fn();
    render(<AITriageStrip ticket={baseTicket} onTicketUpdated={onTicketUpdated} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Apply AI suggestion' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Apply AI suggestion' }));

    await waitFor(() => {
      expect(ticketsApi.updateTicket).toHaveBeenCalledWith(1, {
        category: 'network',
      });
      expect(ticketsApi.confirmTriageFeedback).toHaveBeenCalledWith(1);
    });

    expect(onTicketUpdated).toHaveBeenCalled();
    expect(screen.getByText('AI suggestion applied successfully')).toBeInTheDocument();
  });

  it('Apply admin category and priority: admin clicking Apply calls PATCH with both category and priority', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAdminUser,
      role: mockAdminUser.role,
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(<AITriageStrip ticket={baseTicket} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Apply AI suggestion' })).toBeInTheDocument();
    });

    // Admin should not see the "Priority changes need an admin" warning
    expect(screen.queryByText('Priority changes need an admin')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Apply AI suggestion' }));

    await waitFor(() => {
      expect(ticketsApi.updateTicket).toHaveBeenCalledWith(1, {
        category: 'network',
        priority: 'high',
      });
      expect(ticketsApi.confirmTriageFeedback).toHaveBeenCalledWith(1);
    });

    expect(screen.getByText('AI suggestion applied successfully')).toBeInTheDocument();
  });

  it('Mark reviewed as is: calls POST confirm without PATCH', async () => {
    render(<AITriageStrip ticket={baseTicket} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Mark reviewed as is' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mark reviewed as is' }));

    await waitFor(() => {
      expect(ticketsApi.confirmTriageFeedback).toHaveBeenCalledWith(1);
    });

    expect(ticketsApi.updateTicket).not.toHaveBeenCalled();
    expect(screen.getByText('Marked as reviewed')).toBeInTheDocument();
  });

  it('hides Apply button when ticket already matches suggestion in both category and priority', async () => {
    const matchingTicket: Ticket = {
      ...baseTicket,
      category: 'network',
      priority: 'high',
    };

    render(<AITriageStrip ticket={matchingTicket} />);

    await waitFor(() => {
      expect(screen.getByText('AI Triage')).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: 'Apply AI suggestion' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark reviewed as is' })).toBeInTheDocument();
  });

  it('loading state: buttons disabled while in-flight', async () => {
    let resolveConfirm: (val: TriageFeedbackRead) => void;
    const confirmPromise = new Promise<TriageFeedbackRead>((resolve) => {
      resolveConfirm = resolve;
    });
    vi.mocked(ticketsApi.confirmTriageFeedback).mockReturnValue(confirmPromise);

    render(<AITriageStrip ticket={baseTicket} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Mark reviewed as is' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mark reviewed as is' }));

    // Buttons should now be disabled
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Apply AI suggestion' })).toBeDisabled();

    // Resolve promise
    resolveConfirm!({
      ...baseFeedback,
      final_set_at: '2026-11-01T10:00:00Z',
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Mark reviewed as is' })).not.toBeDisabled();
    });
  });

  it('error state: error from API is handled gracefully (no crash)', async () => {
    vi.mocked(ticketsApi.confirmTriageFeedback).mockRejectedValue(new Error('Network error on confirm'));

    render(<AITriageStrip ticket={baseTicket} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Mark reviewed as is' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mark reviewed as is' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Network error on confirm');
    });

    // Component is still intact and alive
    expect(screen.getByText('AI Triage')).toBeInTheDocument();
  });
});
