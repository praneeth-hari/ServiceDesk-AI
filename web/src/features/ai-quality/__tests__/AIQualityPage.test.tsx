import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AIQualityPage } from '../AIQualityPage';
import * as clientApi from '../../../api/client';
import * as authHook from '../../../context/useAuth';
import type { AIQualityReportResponse, User } from '../../../api/types';

vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual('../../../api/client');
  return {
    ...actual,
    getAIQualityReport: vi.fn(),
  };
});
vi.mock('../../../context/useAuth');

const mockAgentUser: User = {
  id: 20,
  email: 'agent@example.com',
  full_name: 'Bob Agent',
  role: 'agent',
  is_active: true,
  created_at: '2026-10-01T00:00:00Z',
};

const mockRequesterUser: User = {
  id: 10,
  email: 'requester@example.com',
  full_name: 'Alice Requester',
  role: 'requester',
  is_active: true,
  created_at: '2026-10-01T00:00:00Z',
};

const mockFullReport: AIQualityReportResponse = {
  total_suggestions: 120,
  counts_by_method: {
    knn: 80,
    'llm-rag': 40,
  },
  requester_acceptance: {
    category_pct: 75.0,
    priority_pct: 70.0,
    n: 120,
  },
  agent_review: {
    reviewed_n: 50,
    category_agreement_pct: 82.5,
    priority_agreement_pct: 80.0,
    confirmed_n: 38,
    corrected_n: 12,
  },
  weekly: [
    {
      week_start: '2026-10-19',
      n: 40,
      requester_category_acceptance_pct: 70.0,
      agent_category_agreement_pct: 80.0,
    },
    {
      week_start: '2026-10-26',
      n: 80,
      requester_category_acceptance_pct: 77.5,
      agent_category_agreement_pct: 85.0,
    },
  ],
  top_corrections: [
    {
      suggested: 'software',
      final: 'access',
      count: 7,
    },
    {
      suggested: 'hardware',
      final: 'network',
      count: 5,
    },
  ],
  by_method: [
    {
      method: 'knn',
      n: 80,
      reviewed_n: 35,
      category_agreement_pct: 80.0,
    },
    {
      method: 'llm-rag',
      n: 40,
      reviewed_n: 15,
      category_agreement_pct: 86.7,
    },
  ],
};

function renderAIQualityPage() {
  return render(
    <MemoryRouter initialEntries={['/ai-quality']}>
      <Routes>
        <Route path="/ai-quality" element={<AIQualityPage />} />
        <Route path="/tickets" element={<div>Tickets Fallback Page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('AIQualityPage', () => {
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
    vi.mocked(clientApi.getAIQualityReport).mockResolvedValue(mockFullReport);
  });

  it('loaded state: shows all four stat cards and sections when data present', async () => {
    renderAIQualityPage();

    // Title and subtitle
    expect(screen.getByRole('heading', { level: 1, name: 'AI quality' })).toBeInTheDocument();
    expect(screen.getByText(/How often the triage suggestion is accepted/i)).toBeInTheDocument();

    // Card 1: Suggestions made
    expect(await screen.findByText('Suggestions made')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('kNN: 80 | LLM: 40')).toBeInTheDocument();

    // Card 2: Requester kept AI category
    expect(screen.getByText('Requester kept AI category')).toBeInTheDocument();
    expect(screen.getByText('75%')).toBeInTheDocument();
    expect(screen.getByText(/90 of 120 tickets/i)).toBeInTheDocument();

    // Card 3: Agents reviewed
    expect(screen.getByText('Agents reviewed')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('38 confirmed · 12 corrected')).toBeInTheDocument();

    // Card 4: Agent agreement
    expect(screen.getByText('Agent agreement (category)')).toBeInTheDocument();
    expect(screen.getByText('82.5%')).toBeInTheDocument();
    expect(screen.getByText('of 50 reviewed tickets')).toBeInTheDocument();

    // Sections
    expect(screen.getByText('Agreement over time')).toBeInTheDocument();
    expect(screen.getByText('Top corrections')).toBeInTheDocument();
    expect(screen.getByText('By method')).toBeInTheDocument();

    // Top corrections table rows
    expect(screen.getByText('software')).toBeInTheDocument();
    expect(screen.getByText('access')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();

    // By method badges & numbers
    expect(screen.getByText('kNN')).toBeInTheDocument();
    expect(screen.getByText(/80% agreed · 35 reviewed/i)).toBeInTheDocument();
    expect(screen.getByText('LLM')).toBeInTheDocument();
    expect(screen.getByText(/86.7% agreed · 15 reviewed/i)).toBeInTheDocument();
  });

  it('null values show No data yet: when category_pct is null, shows No data yet', async () => {
    const reportWithNulls: AIQualityReportResponse = {
      ...mockFullReport,
      requester_acceptance: {
        category_pct: null,
        priority_pct: null,
        n: 0,
      },
      agent_review: {
        reviewed_n: 0,
        category_agreement_pct: null,
        priority_agreement_pct: null,
        confirmed_n: 0,
        corrected_n: 0,
      },
    };

    vi.mocked(clientApi.getAIQualityReport).mockResolvedValue(reportWithNulls);

    renderAIQualityPage();

    await waitFor(() => {
      expect(screen.getByText('Suggestions made')).toBeInTheDocument();
    });

    // Both requester and agent agreement should display "No data yet"
    const noDataElements = screen.getAllByText('No data yet');
    expect(noDataElements.length).toBeGreaterThanOrEqual(2);
  });


  it('displays small sample note when n < 10 or reviewed_n < 10', async () => {
    const smallSampleReport: AIQualityReportResponse = {
      ...mockFullReport,
      requester_acceptance: {
        category_pct: 66.7,
        priority_pct: 50.0,
        n: 6,
      },
      agent_review: {
        reviewed_n: 3,
        category_agreement_pct: 100.0,
        priority_agreement_pct: 66.7,
        confirmed_n: 2,
        corrected_n: 1,
      },
    };

    vi.mocked(clientApi.getAIQualityReport).mockResolvedValue(smallSampleReport);

    renderAIQualityPage();

    await waitFor(() => {
      expect(screen.getByText('Suggestions made')).toBeInTheDocument();
    });

    const smallSampleNotes = screen.getAllByText('Small sample, treat as indicative only');
    expect(smallSampleNotes.length).toBe(2);
  });

  it('empty state: when total_suggestions == 0, shows empty state message', async () => {
    const emptyReport: AIQualityReportResponse = {
      total_suggestions: 0,
      counts_by_method: {},
      requester_acceptance: {
        category_pct: null,
        priority_pct: null,
        n: 0,
      },
      agent_review: {
        reviewed_n: 0,
        category_agreement_pct: null,
        priority_agreement_pct: null,
        confirmed_n: 0,
        corrected_n: 0,
      },
      weekly: [],
      top_corrections: [],
      by_method: [],
    };

    vi.mocked(clientApi.getAIQualityReport).mockResolvedValue(emptyReport);

    renderAIQualityPage();

    await waitFor(() => {
      expect(
        screen.getByText(/Figures appear once tickets are created with an AI triage suggestion\./i)
      ).toBeInTheDocument();
    });

    expect(screen.queryByText('Suggestions made')).not.toBeInTheDocument();
  });

  it('requester redirect: when user is requester, redirected away', async () => {
    vi.mocked(authHook.useAuth).mockReturnValue({
      user: mockRequesterUser,
      role: mockRequesterUser.role,
      token: 'fake-token',
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    renderAIQualityPage();

    // Should redirect to /tickets
    await waitFor(() => {
      expect(screen.getByText('Tickets Fallback Page')).toBeInTheDocument();
    });

    expect(screen.queryByRole('heading', { name: 'AI quality' })).not.toBeInTheDocument();
    expect(clientApi.getAIQualityReport).not.toHaveBeenCalled();
  });

  it('table toggle: clicking View as table shows tabular data', async () => {
    renderAIQualityPage();

    await waitFor(() => {
      expect(screen.getByText('Agreement over time')).toBeInTheDocument();
    });

    const toggleButton = screen.getByRole('button', { name: /View Agreement over time as table/i });
    expect(toggleButton).toBeInTheDocument();

    fireEvent.click(toggleButton);

    // Table should now be visible
    expect(screen.getByRole('table', { name: /Agreement over time table/i })).toBeInTheDocument();
    expect(screen.getByText('2026-10-19')).toBeInTheDocument();
    expect(screen.getByText('2026-10-26')).toBeInTheDocument();

    // Toggle back to chart
    const chartButton = screen.getByRole('button', { name: /View Agreement over time as chart/i });
    fireEvent.click(chartButton);

    expect(screen.queryByRole('table', { name: /Agreement over time table/i })).not.toBeInTheDocument();
  });

  it('time range selector requests data with updated days param', async () => {
    renderAIQualityPage();

    await waitFor(() => {
      expect(clientApi.getAIQualityReport).toHaveBeenCalledWith(30);
    });

    const button7d = screen.getByRole('button', { name: 'Show 7 days' });
    fireEvent.click(button7d);

    await waitFor(() => {
      expect(clientApi.getAIQualityReport).toHaveBeenCalledWith(7);
    });
  });
});
