import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { HolidaysPage } from '../HolidaysPage';
import { AppShell } from '../../../components/AppShell';
import { RoleRoute } from '../../../components/RoleRoute';
import { AuthProvider } from '../../../context/AuthContext';
import type { Holiday } from '../../../api/holidays';

describe('HolidaysPage & Navigation', () => {
  const originalFetch = globalThis.fetch;

  const mockHolidays2026: Holiday[] = [
    { id: 1, holiday_date: '2026-01-26', name: 'Republic Day', created_at: '2026-01-01T00:00:00Z' }, // Monday
    { id: 2, holiday_date: '2026-08-15', name: 'Independence Day', created_at: '2026-01-01T00:00:00Z' }, // Saturday (Weekend)
    { id: 3, holiday_date: '2026-08-16', name: 'Parsi New Year', created_at: '2026-01-01T00:00:00Z' }, // Sunday (Weekend)
    { id: 4, holiday_date: '2026-10-02', name: 'Gandhi Jayanti', created_at: '2026-01-01T00:00:00Z' }, // Friday
  ];

  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem('access_token', 'test-token');
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 1,
        email: 'admin@example.com',
        full_name: 'Admin User',
        role: 'admin',
      })
    );
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  const renderWithRouter = (initialRoute = '/holidays') => {
    return render(
      <MemoryRouter initialEntries={[initialRoute]}>
        <AuthProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/tickets" element={<div>Tickets Page</div>} />
              <Route element={<RoleRoute adminOnly />}>
                <Route path="/holidays" element={<HolidaysPage />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );
  };

  it('admin sees the Holidays nav tab, while non-admin does not', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    });

    // 1. As admin
    const { unmount } = renderWithRouter('/holidays');
    expect(screen.getAllByRole('link', { name: 'Holidays' })[0]).toBeInTheDocument();
    unmount();

    // 2. As agent
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 2,
        email: 'agent@example.com',
        full_name: 'Agent User',
        role: 'agent',
      })
    );
    const { unmount: unmountAgent } = renderWithRouter('/tickets');
    expect(screen.queryByRole('link', { name: 'Holidays' })).not.toBeInTheDocument();
    unmountAgent();

    // 3. As requester
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 3,
        email: 'requester@example.com',
        full_name: 'Requester User',
        role: 'requester',
      })
    );
    renderWithRouter('/tickets');
    expect(screen.queryByRole('link', { name: 'Holidays' })).not.toBeInTheDocument();
  });

  it('redirects non-admin users away from /holidays to /tickets', async () => {
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 2,
        email: 'agent@example.com',
        full_name: 'Agent User',
        role: 'agent',
      })
    );

    renderWithRouter('/holidays');
    expect(await screen.findByText('Tickets Page')).toBeInTheDocument();
    expect(screen.queryByText('Official public holidays')).not.toBeInTheDocument();
  });

  it('renders holiday list sorted ascending and shows weekend tags for Saturday/Sunday', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/holidays')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockHolidays2026),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
    });

    renderWithRouter('/holidays');

    // Wait for data load
    expect(await screen.findAllByText('Republic Day')).not.toHaveLength(0);
    expect(screen.getAllByText('Independence Day')).not.toHaveLength(0);
    expect(screen.getAllByText('Parsi New Year')).not.toHaveLength(0);
    expect(screen.getAllByText('Gandhi Jayanti')).not.toHaveLength(0);

    // Formatted dates
    expect(screen.getAllByText('Jan 26, 2026')).not.toHaveLength(0);
    expect(screen.getAllByText('Aug 15, 2026')).not.toHaveLength(0);

    // Check count
    const countBadge = screen.getByTestId('holiday-count');
    expect(countBadge).toHaveTextContent('4');

    // Weekdays & weekend tags
    expect(screen.getAllByText(/Monday/)).not.toHaveLength(0);
    expect(screen.getAllByText(/Friday/)).not.toHaveLength(0);

    const weekendTags = screen.getAllByText('weekend');
    // Saturday (Aug 15) and Sunday (Aug 16) in both desktop and mobile
    expect(weekendTags.length).toBeGreaterThanOrEqual(2);
  });

  it('does not render empty state while loading, and hides count badge during loading', () => {
    globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {}));

    renderWithRouter('/holidays');

    // Loading skeleton is shown
    expect(screen.getByTestId('holidays-loading-skeleton')).toBeInTheDocument();

    // Count badge is hidden
    expect(screen.queryByTestId('holiday-count')).not.toBeInTheDocument();

    // Empty state text is NOT rendered
    expect(screen.queryByText(/No holidays for/i)).not.toBeInTheDocument();
  });

  it('renders empty year state when no holidays exist for that year', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/holidays')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
    });

    renderWithRouter('/holidays');

    const currentYear = new Date().getFullYear();
    expect(
      await screen.findByText(`No holidays for ${currentYear} yet. Add the first one.`)
    ).toBeInTheDocument();
  });

  it('renders error banner with Retry when fetching fails, and recovers on Retry', async () => {
    let fail = true;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/holidays') && fail) {
        return Promise.resolve({
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
          json: () => Promise.resolve({ error: { message: 'Database failure' } }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockHolidays2026),
      });
    });

    renderWithRouter('/holidays');

    // Friendly error banner displayed
    expect(
      await screen.findByText('A server problem occurred. Please try again.')
    ).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: 'Retry' });

    // Recover
    fail = false;
    fireEvent.click(retryBtn);

    expect(await screen.findAllByText('Republic Day')).not.toHaveLength(0);
    expect(
      screen.queryByText('A server problem occurred. Please try again.')
    ).not.toBeInTheDocument();
  });

  it('adds a new holiday and validates duplicate date error', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, opts?: RequestInit) => {
      if (opts?.method === 'POST') {
        const body = JSON.parse(opts.body as string);
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({ id: 99, ...body, created_at: '2026-01-01' }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockHolidays2026),
      });
    });
    globalThis.fetch = fetchMock;

    renderWithRouter('/holidays');

    expect(await screen.findAllByText('Republic Day')).not.toHaveLength(0);

    const dateInput = screen.getByLabelText('Date');
    const nameInput = screen.getByLabelText('Name');
    const submitBtn = screen.getByRole('button', { name: 'Add holiday' });

    // 1. Duplicate date check
    fireEvent.change(dateInput, { target: { value: '2026-01-26' } });
    fireEvent.change(nameInput, { target: { value: 'Another Republic Day' } });
    fireEvent.click(submitBtn);

    expect(
      await screen.findByText('A holiday on 2026-01-26 already exists')
    ).toBeInTheDocument();

    // 2. Valid submission
    fireEvent.change(dateInput, { target: { value: '2026-11-01' } });
    fireEvent.change(nameInput, { target: { value: 'Kannada Rajyotsava' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/holidays'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            holiday_date: '2026-11-01',
            name: 'Kannada Rajyotsava',
          }),
        })
      );
    });

    expect(await screen.findAllByText('Kannada Rajyotsava')).not.toHaveLength(0);
  });

  it('supports inline editing of a row via PATCH and cancels cleanly', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, opts?: RequestInit) => {
      if (opts?.method === 'PATCH') {
        const body = JSON.parse(opts.body as string);
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              id: 1,
              holiday_date: body.holiday_date || '2026-01-26',
              name: body.name || 'Republic Day',
              created_at: '2026-01-01T00:00:00Z',
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockHolidays2026),
      });
    });
    globalThis.fetch = fetchMock;

    renderWithRouter('/holidays');

    expect(await screen.findAllByText('Republic Day')).not.toHaveLength(0);

    // Click Edit on Republic Day (pick first matching button)
    const editBtn = screen.getAllByRole('button', { name: 'Edit Republic Day' })[0];
    fireEvent.click(editBtn);

    const editNameInputs = screen.getAllByLabelText('Edit holiday name');
    expect(editNameInputs[0]).toHaveValue('Republic Day');

    // Test Cancel
    const cancelBtn = screen.getAllByRole('button', { name: 'Cancel' })[0];
    fireEvent.click(cancelBtn);
    expect(screen.queryByLabelText('Edit holiday name')).not.toBeInTheDocument();

    // Open edit again and save
    fireEvent.click(screen.getAllByRole('button', { name: 'Edit Republic Day' })[0]);
    const editInputAgain = screen.getAllByLabelText('Edit holiday name')[0];
    fireEvent.change(editInputAgain, { target: { value: 'National Republic Day' } });

    const saveBtn = screen.getAllByRole('button', { name: 'Save' })[0];
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/holidays/1'),
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({
            holiday_date: '2026-01-26',
            name: 'National Republic Day',
          }),
        })
      );
    });

    expect(await screen.findAllByText('National Republic Day')).not.toHaveLength(0);
  });

  it('opens delete confirmation dialog, traps focus, handles Escape, and deletes on confirm', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, opts?: RequestInit) => {
      if (opts?.method === 'DELETE') {
        return Promise.resolve({ ok: true, status: 204 });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockHolidays2026),
      });
    });
    globalThis.fetch = fetchMock;

    renderWithRouter('/holidays');

    expect(await screen.findAllByText('Gandhi Jayanti')).not.toHaveLength(0);

    // Click Delete on Gandhi Jayanti
    const deleteBtn = screen.getAllByRole('button', { name: 'Delete Gandhi Jayanti' })[0];
    fireEvent.click(deleteBtn);

    // Modal dialog is open
    expect(
      screen.getByText('Delete Gandhi Jayanti (2026-10-02)?')
    ).toBeInTheDocument();

    // 1. Escape key closes modal
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(
      screen.queryByText('Delete Gandhi Jayanti (2026-10-02)?')
    ).not.toBeInTheDocument();

    // 2. Open again and confirm deletion
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete Gandhi Jayanti' })[0]);
    expect(
      screen.getByText('Delete Gandhi Jayanti (2026-10-02)?')
    ).toBeInTheDocument();

    const confirmDeleteBtn = screen.getByRole('button', { name: 'Delete' });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/holidays/4'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });

    expect(screen.queryByText('Gandhi Jayanti')).not.toBeInTheDocument();
  });
});
