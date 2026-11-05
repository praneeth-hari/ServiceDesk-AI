import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { UsersPage } from '../UsersPage';
import { AppShell } from '../../../components/AppShell';
import { RoleRoute } from '../../../components/RoleRoute';
import { AuthProvider } from '../../../context/AuthContext';
import type { UserListResponse } from '../../../api/types';

describe('UsersPage & Navigation', () => {
  const originalFetch = globalThis.fetch;

  const userRows = [
    {
      id: 1,
      full_name: 'System Admin',
      email: 'admin@example.com',
      role: 'admin' as const,
      is_active: true,
      created_at: '2026-10-25T10:00:00Z',
      open_assigned_count: 0,
    },
    {
      id: 2,
      full_name: 'Asha Agent',
      email: 'agent@example.com',
      role: 'agent' as const,
      is_active: true,
      created_at: '2026-10-25T11:00:00Z',
      open_assigned_count: 4,
    },
    {
      id: 3,
      full_name: 'Ravi Requester',
      email: 'requester@example.com',
      role: 'requester' as const,
      is_active: false,
      created_at: '2026-10-25T12:00:00Z',
      open_assigned_count: 0,
    },
  ];

  const mockUsersResponse: UserListResponse = {
    total: 3,
    active_count: 2,
    active: 2,
    rows: userRows,
    users: userRows,
  };

  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem('access_token', 'test-token');
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 1,
        email: 'admin@example.com',
        full_name: 'System Admin',
        role: 'admin',
      })
    );
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  const renderWithRouter = (initialRoute = '/users') => {
    return render(
      <MemoryRouter initialEntries={[initialRoute]}>
        <AuthProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/tickets" element={<div>Tickets Page Screen</div>} />
              <Route element={<RoleRoute adminOnly />}>
                <Route path="/users" element={<UsersPage />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );
  };

  it('Users nav is visible to admin only, and non-admin is redirected from /users', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    // 1. As admin: Sees Users nav tab and page loads
    const { unmount } = renderWithRouter('/users');
    expect(screen.getAllByRole('link', { name: 'Users' })[0]).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Users' })).toBeInTheDocument();
    });
    unmount();

    // 2. As requester: Nav link is hidden and /users redirects to /tickets
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 3,
        email: 'requester@example.com',
        full_name: 'Ravi Requester',
        role: 'requester',
      })
    );
    renderWithRouter('/users');
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Tickets Page Screen')).toBeInTheDocument();
    });
  });

  it('renders list rows and summary line with total and active count', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    renderWithRouter('/users');

    // Verify summary line
    await waitFor(() => {
      expect(
        screen.getByText(/Manage who can sign in and what they can do\./i)
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/3 users/i)).toBeInTheDocument();
    expect(screen.getByText(/2 active/i)).toBeInTheDocument();

    // Verify user rows rendered (System Admin appears in AppShell header and table row)
    expect(screen.getAllByText('System Admin').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Asha Agent')).toBeInTheDocument();
    expect(screen.getByText('Ravi Requester')).toBeInTheDocument();

    // Inactive user has Inactive pill and Reactivate button
    expect(screen.getAllByText('Inactive').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('button', { name: 'Reactivate' })).toBeInTheDocument();

    // Notice footer text
    expect(
      screen.getByText(/Your own row is locked so you cannot demote or deactivate yourself\./i)
    ).toBeInTheDocument();
  });

  it('locks the signed-in admin own row with YOU tag and disabled controls', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    renderWithRouter('/users');

    await waitFor(() => {
      expect(screen.getAllByText('System Admin').length).toBeGreaterThanOrEqual(1);
    });

    // "YOU" tag
    expect(screen.getByText('YOU')).toBeInTheDocument();

    // Role select for System Admin is disabled
    const adminSelect = screen.getByLabelText('Role for System Admin') as HTMLSelectElement;
    expect(adminSelect).toBeDisabled();
    expect(adminSelect).toHaveAttribute(
      'title',
      'Your own row is locked so you cannot demote yourself'
    );

    // Deactivate button on own row is disabled
    const ownDeactBtn = screen.getByTitle(
      'Your own row is locked so you cannot deactivate yourself'
    );
    expect(ownDeactBtn).toBeDisabled();
  });

  it('searches and filters users via API params', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });
    globalThis.fetch = fetchMock;

    renderWithRouter('/users');

    await waitFor(() => {
      expect(screen.getAllByText('System Admin').length).toBeGreaterThanOrEqual(1);
    });

    // Type in search box
    const searchInput = screen.getByLabelText('Search users');
    await user.type(searchInput, 'Asha');

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((call) => call[0] as string);
      expect(calls.some((c) => c.includes('q=Asha'))).toBe(true);
    });

    // Change role filter
    const roleSelect = screen.getByLabelText('Filter by role');
    fireEvent.change(roleSelect, { target: { value: 'agent' } });

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((call) => call[0] as string);
      expect(calls.some((c) => c.includes('role=agent'))).toBe(true);
    });

    // Change status filter
    const statusSelect = screen.getByLabelText('Filter by status');
    fireEvent.change(statusSelect, { target: { value: 'inactive' } });

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((call) => call[0] as string);
      expect(calls.some((c) => c.includes('is_active=false'))).toBe(true);
    });
  });

  it('add user modal opens, handles 409 conflict inline, and succeeds on valid submit', async () => {
    const user = userEvent.setup();
    let postCallCount = 0;

    globalThis.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/users') && options?.method === 'POST') {
        postCallCount++;
        const body = JSON.parse(options.body as string);
        if (body.email === 'taken@example.com') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ error: { message: 'Email already registered' } }),
              { status: 409, headers: { 'Content-Type': 'application/json' } }
            )
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 4,
              full_name: body.full_name,
              email: body.email,
              role: body.role,
              is_active: true,
              created_at: '2026-10-25T14:00:00Z',
              open_assigned_count: 0,
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    renderWithRouter('/users');

    await waitFor(() => {
      expect(screen.getAllByText('System Admin').length).toBeGreaterThanOrEqual(1);
    });

    // Open add user modal
    await user.click(screen.getByRole('button', { name: '+ Add user' }));
    expect(screen.getByRole('heading', { name: 'Add user' })).toBeInTheDocument();

    // Try submitting with taken email
    await user.type(screen.getByLabelText('Full name'), 'New Person');
    await user.type(screen.getByLabelText('Email'), 'taken@example.com');
    await user.type(screen.getByLabelText(/Password/), 'ValidPassword123!');
    await user.click(screen.getByRole('button', { name: 'Create user' }));

    // Inline 409 error shown
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Email already in use/i);
    });

    // Fix email to fresh address
    const emailInput = screen.getByLabelText('Email');
    await user.clear(emailInput);
    await user.type(emailInput, 'fresh@example.com');
    await user.click(screen.getByRole('button', { name: 'Create user' }));

    // Modal closes on success
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Add user' })).not.toBeInTheDocument();
    });
    expect(postCallCount).toBe(2);
  });

  it('role change calls API and reverts on server error', async () => {
    let patchCalled = false;
    globalThis.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/role') && options?.method === 'PATCH') {
        patchCalled = true;
        return Promise.resolve(
          new Response(
            JSON.stringify({ error: { message: 'Cannot demote the last active admin' } }),
            { status: 400, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    renderWithRouter('/users');

    await waitFor(() => {
      expect(screen.getByText('Asha Agent')).toBeInTheDocument();
    });

    const ashaSelect = screen.getByLabelText('Role for Asha Agent') as HTMLSelectElement;
    expect(ashaSelect.value).toBe('agent');

    // Change to requester
    fireEvent.change(ashaSelect, { target: { value: 'requester' } });

    await waitFor(() => {
      expect(patchCalled).toBe(true);
      expect(screen.getByRole('alert')).toHaveTextContent('Cannot demote the last active admin');
    });
  });

  it('deactivate dialog shows open tickets warning when count > 0 and confirm calls API', async () => {
    const user = userEvent.setup();
    let statusPatchCalled = false;

    globalThis.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/status') && options?.method === 'PATCH') {
        statusPatchCalled = true;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 2,
              full_name: 'Asha Agent',
              email: 'agent@example.com',
              role: 'agent',
              is_active: false,
              created_at: '2026-10-25T11:00:00Z',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    renderWithRouter('/users');

    await waitFor(() => {
      expect(screen.getByText('Asha Agent')).toBeInTheDocument();
    });

    // Click Deactivate on Asha Agent row (open_assigned_count = 4)
    const ashaRow = screen.getByText('Asha Agent').closest('tr')!;
    const deactBtn = ashaRow.querySelector('button')!;
    await user.click(deactBtn);

    // Deactivate dialog opens
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Deactivate Asha Agent?' })).toBeInTheDocument();
    });

    // Warning note about 4 open tickets is displayed
    const warningNote = screen.getByRole('note');
    expect(warningNote).toHaveTextContent(/Asha Agent has 4 open tickets assigned to them\./i);

    // Confirm deactivate inside dialog
    const dialog = screen.getByRole('dialog');
    const confirmBtn = within(dialog).getByRole('button', { name: 'Deactivate' });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(statusPatchCalled).toBe(true);
      expect(screen.queryByRole('heading', { name: 'Deactivate Asha Agent?' })).not.toBeInTheDocument();
    });
  });

  it('reactivate button calls API directly without confirmation dialog', async () => {
    const user = userEvent.setup();
    let reactivateCalled = false;

    globalThis.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/status') && options?.method === 'PATCH') {
        reactivateCalled = true;
        const body = JSON.parse(options.body as string);
        expect(body.is_active).toBe(true);
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 3,
              full_name: 'Ravi Requester',
              email: 'requester@example.com',
              role: 'requester',
              is_active: true,
              created_at: '2026-10-25T12:00:00Z',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    renderWithRouter('/users');

    await waitFor(() => {
      expect(screen.getByText('Ravi Requester')).toBeInTheDocument();
    });

    // Click Reactivate on Ravi Requester row
    const reactivateBtn = screen.getByRole('button', { name: 'Reactivate' });
    await user.click(reactivateBtn);

    await waitFor(() => {
      expect(reactivateCalled).toBe(true);
    });

    // Confirm NO dialog was opened
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes dialogs when Escape key is pressed', async () => {
    const user = userEvent.setup();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/users/admin')) {
        return Promise.resolve(new Response(JSON.stringify(mockUsersResponse), { status: 200 }));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    renderWithRouter('/users');

    await waitFor(() => {
      expect(screen.getAllByText('System Admin').length).toBeGreaterThanOrEqual(1);
    });

    // Open add user modal
    await user.click(screen.getByRole('button', { name: '+ Add user' }));
    expect(screen.getByRole('heading', { name: 'Add user' })).toBeInTheDocument();

    // Press Escape
    fireEvent.keyDown(window, { key: 'Escape' });

    // Dialog closes
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Add user' })).not.toBeInTheDocument();
    });
  });
});
