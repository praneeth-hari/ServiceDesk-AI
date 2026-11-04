import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AIAssistCard } from '../AIAssistCard';
import * as clientApi from '../../../api/client';
import * as authHook from '../../../context/useAuth';
import type { User, AIAssistSummaryResponse, AIAssistReplyResponse } from '../../../api/types';

vi.mock('../../../api/client');
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

describe('AIAssistCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing for requester users and does not call status endpoint', () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockRequesterUser,
      role: mockRequesterUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    const { container } = render(
      <AIAssistCard ticketId={1} onInsertReply={vi.fn()} />
    );

    expect(container).toBeEmptyDOMElement();
    expect(clientApi.getAIAssistStatus).not.toHaveBeenCalled();
  });

  it('renders disabled state card when AI_ASSIST_MODE is off', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    vi.mocked(clientApi.getAIAssistStatus).mockResolvedValue({
      enabled: false,
      mode: 'off',
      model: null,
    });

    render(<AIAssistCard ticketId={1} onInsertReply={vi.fn()} />);

    expect(await screen.findByTestId('ai-assist-card-disabled')).toBeInTheDocument();
    expect(screen.getByText(/AI assist is disabled on this server/i)).toBeInTheDocument();
  });

  it('renders enabled state with model badge and action buttons', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    vi.mocked(clientApi.getAIAssistStatus).mockResolvedValue({
      enabled: true,
      mode: 'ollama',
      model: 'llama3.1:8b',
    });

    render(<AIAssistCard ticketId={1} onInsertReply={vi.fn()} />);

    expect(await screen.findByTestId('ai-assist-card')).toBeInTheDocument();
    expect(screen.getByTestId('ai-assist-model-badge')).toHaveTextContent('llama3.1:8b');
    expect(screen.getByRole('button', { name: /Summarize/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Draft reply/i })).toBeInTheDocument();
  });

  it('handles Summarize flow with key facts and latency', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    vi.mocked(clientApi.getAIAssistStatus).mockResolvedValue({
      enabled: true,
      mode: 'ollama',
      model: 'llama3.1:8b',
    });

    const summaryResponse: AIAssistSummaryResponse = {
      task: 'summary',
      summary: 'User cannot connect to corporate VPN after password reset.',
      facts: [
        { label: 'OS', value: 'macOS 14.5' },
        { label: 'Client', value: 'OpenVPN 3.2' },
      ],
      model: 'llama3.1:8b',
      latency_ms: 1420,
    };

    vi.mocked(clientApi.requestAIAssist).mockResolvedValue(summaryResponse);

    render(<AIAssistCard ticketId={1} onInsertReply={vi.fn()} />);

    const summarizeBtn = await screen.findByRole('button', { name: /Summarize/i });
    fireEvent.click(summarizeBtn);

    expect(screen.getByText(/Generating…/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Issue Summary')).toBeInTheDocument();
    });

    expect(screen.getByText('User cannot connect to corporate VPN after password reset.')).toBeInTheDocument();
    expect(screen.getByText('OS:')).toBeInTheDocument();
    expect(screen.getByText('macOS 14.5')).toBeInTheDocument();
    expect(screen.getByText('Client:')).toBeInTheDocument();
    expect(screen.getByText('OpenVPN 3.2')).toBeInTheDocument();
    expect(screen.getByText('Generated in 1.4s')).toBeInTheDocument();
    expect(clientApi.requestAIAssist).toHaveBeenCalledWith(1, 'summary');
  });

  it('handles Draft reply flow and Insert into reply callback', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    vi.mocked(clientApi.getAIAssistStatus).mockResolvedValue({
      enabled: true,
      mode: 'ollama',
      model: 'llama3.1:8b',
    });

    const replyResponse: AIAssistReplyResponse = {
      task: 'reply',
      reply: 'Hi Alice,\n\nPlease try clearing your browser cookies.\n\nRegards,\nBob',
      model: 'llama3.1:8b',
      latency_ms: 2150,
    };

    vi.mocked(clientApi.requestAIAssist).mockResolvedValue(replyResponse);

    const onInsertReply = vi.fn();
    render(<AIAssistCard ticketId={1} onInsertReply={onInsertReply} />);

    const replyBtn = await screen.findByRole('button', { name: /Draft reply/i });
    fireEvent.click(replyBtn);

    await waitFor(() => {
      expect(screen.getByText('Draft Reply')).toBeInTheDocument();
    });

    expect(screen.getByText('Draft only. Review before posting.')).toBeInTheDocument();
    expect(screen.getByText(/Please try clearing your browser cookies/)).toBeInTheDocument();
    expect(screen.getByText(/Generated in 2\.[12]s/)).toBeInTheDocument();

    const insertBtn = screen.getByRole('button', { name: /Insert into reply/i });
    fireEvent.click(insertBtn);

    expect(onInsertReply).toHaveBeenCalledWith(replyResponse.reply);
    expect(screen.getByText('Inserted into composer!')).toBeInTheDocument();
  });

  it('displays error alert on failure and dismisses it', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    vi.mocked(clientApi.getAIAssistStatus).mockResolvedValue({
      enabled: true,
      mode: 'ollama',
      model: 'llama3.1:8b',
    });

    vi.mocked(clientApi.requestAIAssist).mockRejectedValue(new Error('AI assist is currently unavailable.'));

    render(<AIAssistCard ticketId={1} onInsertReply={vi.fn()} />);

    const summarizeBtn = await screen.findByRole('button', { name: /Summarize/i });
    fireEvent.click(summarizeBtn);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/AI assist is currently unavailable/i);

    const dismissBtn = screen.getByRole('button', { name: /Dismiss/i });
    fireEvent.click(dismissBtn);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('shows loading state with buttons disabled, "Generating…", and cold start note shown', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    vi.mocked(clientApi.getAIAssistStatus).mockResolvedValue({
      enabled: true,
      mode: 'ollama',
      model: 'llama3.1:8b',
    });

    // Never resolves during this assertion
    vi.mocked(clientApi.requestAIAssist).mockReturnValue(new Promise(() => {}));

    render(<AIAssistCard ticketId={1} onInsertReply={vi.fn()} />);

    const summarizeBtn = await screen.findByRole('button', { name: /Summarize/i });
    const draftBtn = screen.getByRole('button', { name: /Draft reply/i });

    fireEvent.click(summarizeBtn);

    // Buttons are disabled during loading
    expect(summarizeBtn).toBeDisabled();
    expect(draftBtn).toBeDisabled();

    // "Generating…" and cold start note are shown
    expect(screen.getByText(/Generating…/i)).toBeInTheDocument();
    expect(screen.getByText(/cold start can take ~15s on first run/i)).toBeInTheDocument();
  });

  it('shows unavailable state when status call fails instead of a blank gap', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockAgentUser,
      role: mockAgentUser.role,
      token: 'token',
      login: vi.fn(),
      logout: vi.fn(),
      isLoading: false,
    });

    // Status call fails
    vi.mocked(clientApi.getAIAssistStatus).mockRejectedValue(new Error('Server error'));

    const { container } = render(<AIAssistCard ticketId={1} onInsertReply={vi.fn()} />);

    // Shows the disabled / unavailable card rather than an empty DOM gap
    expect(await screen.findByTestId('ai-assist-card-disabled')).toBeInTheDocument();
    expect(screen.getByText(/AI assist is disabled on this server/i)).toBeInTheDocument();
    expect(container.firstChild).not.toBeNull();
  });
});

