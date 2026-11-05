import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LoginPage } from '../LoginPage';
import { AuthProvider } from '../../context/AuthContext';

describe('LoginPage', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('login success stores the session and navigates', async () => {
    const user = userEvent.setup();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/login')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: 'valid-jwt-token',
              token_type: 'bearer',
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        );
      }
      if (url.includes('/users/me')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 2,
              email: 'agent@example.com',
              full_name: 'Asha Agent',
              role: 'agent',
              is_active: true,
              created_at: '2026-10-25T11:00:00',
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        );
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/tickets" element={<div>Tickets Dashboard Screen</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitBtn = screen.getByRole('button', { name: /^sign in$/i });

    await user.type(emailInput, 'agent@example.com');
    await user.type(passwordInput, 'AgentPassword123!');
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Tickets Dashboard Screen')).toBeInTheDocument();
    });

    expect(sessionStorage.getItem('access_token')).toBe('valid-jwt-token');
    expect(sessionStorage.getItem('user')).toContain('agent@example.com');
  });

  it('login failure shows the error', async () => {
    const user = userEvent.setup();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/login')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: { message: 'Invalid email or password' },
            }),
            {
              status: 401,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        );
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitBtn = screen.getByRole('button', { name: /^sign in$/i });

    await user.type(emailInput, 'agent@example.com');
    await user.type(passwordInput, 'WrongPassword!');
    await user.click(submitBtn);

    await waitFor(() => {
      const errorAlert = screen.getByRole('alert');
      expect(errorAlert).toBeInTheDocument();
      expect(errorAlert).toHaveTextContent('Invalid email or password.');
    });

    expect(sessionStorage.getItem('access_token')).toBeNull();
  });

  it('login shows cannot reach server message on a 500 server error', async () => {
    const user = userEvent.setup();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/login')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: { message: 'Internal Server Error' },
            }),
            {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            }
          )
        );
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitBtn = screen.getByRole('button', { name: /^sign in$/i });

    await user.type(emailInput, 'agent@example.com');
    await user.type(passwordInput, 'AnyPassword123!');
    await user.click(submitBtn);

    await waitFor(() => {
      const errorAlert = screen.getByRole('alert');
      expect(errorAlert).toBeInTheDocument();
      expect(errorAlert).toHaveTextContent('Cannot reach the server. Please try again.');
    });

    expect(sessionStorage.getItem('access_token')).toBeNull();
  });

  it('login shows cannot reach server message on a network error', async () => {
    const user = userEvent.setup();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/login')) {
        return Promise.reject(new TypeError('Failed to fetch'));
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitBtn = screen.getByRole('button', { name: /^sign in$/i });

    await user.type(emailInput, 'agent@example.com');
    await user.type(passwordInput, 'AnyPassword123!');
    await user.click(submitBtn);

    await waitFor(() => {
      const errorAlert = screen.getByRole('alert');
      expect(errorAlert).toBeInTheDocument();
      expect(errorAlert).toHaveTextContent('Cannot reach the server. Please try again.');
    });

    expect(sessionStorage.getItem('access_token')).toBeNull();
  });

  it('demo section hidden when getDemoAccounts returns enabled: false', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/demo-accounts')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: false,
              accounts: [],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    expect(screen.getByRole('heading', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.queryByText(/or try a demo account/i)).not.toBeInTheDocument();
    expect(screen.getByText('Demo accounts work on local installs only')).toBeInTheDocument();
  });

  it('demo section shown when enabled with demo cards', async () => {
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/demo-accounts')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              accounts: [
                { role: 'requester', name: 'Ravi Requester', description: 'Raise tickets' },
                { role: 'agent', name: 'Asha Agent', description: 'Triage incoming tickets' },
                { role: 'admin', name: 'System Admin', description: 'Manage users' },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/or try a demo account/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Ravi Requester')).toBeInTheDocument();
    expect(screen.getByText('Asha Agent')).toBeInTheDocument();
    expect(screen.getByText('System Admin')).toBeInTheDocument();
    expect(
      screen.getByText('Demo mode is on. Public demo only: accounts hold sample data.')
    ).toBeInTheDocument();
  });

  it('clicking a demo card calls demoLogin and navigates', async () => {
    const user = userEvent.setup();

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/demo-accounts')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              accounts: [
                { role: 'agent', name: 'Asha Agent', description: 'Triage incoming tickets' },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (url.includes('/auth/demo-login')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: 'demo-jwt-token-agent',
              token_type: 'bearer',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (url.includes('/users/me')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 2,
              email: 'agent@example.com',
              full_name: 'Asha Agent',
              role: 'agent',
              is_active: true,
              created_at: '2026-10-25T11:00:00',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/tickets" element={<div>Tickets Dashboard Screen</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    const demoCard = await screen.findByRole('button', { name: /Demo sign in as Asha Agent/i });
    await user.click(demoCard);

    await waitFor(() => {
      expect(screen.getByText('Tickets Dashboard Screen')).toBeInTheDocument();
    });

    expect(sessionStorage.getItem('access_token')).toBe('demo-jwt-token-agent');
    expect(sessionStorage.getItem('user')).toContain('Asha Agent');
  });

  it('429 shows notice, disabled button and countdown that ticks and re-enables at zero while demo cards remain enabled', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] });

    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/auth/demo-accounts')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              accounts: [
                { role: 'agent', name: 'Asha Agent', description: 'Triage incoming tickets' },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          )
        );
      }
      if (url.includes('/auth/login')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              detail: 'Too many failed sign-in attempts. Please try again later.',
              retry_after_seconds: 3,
            }),
            {
              status: 429,
              headers: {
                'Content-Type': 'application/json',
                'Retry-After': '3',
              },
            }
          )
        );
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    // Allow demo accounts effect to resolve
    await act(async () => {
      await Promise.resolve();
    });

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitBtn = screen.getByRole('button', { name: /^sign in$/i });
    const demoCard = screen.getByRole('button', { name: /Demo sign in as Asha Agent/i });

    fireEvent.change(emailInput, { target: { value: 'agent@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'WrongPass!' } });
    fireEvent.click(submitBtn);

    // Wait for 429 response to process
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    // Amber notice is displayed
    const notice = screen.getByRole('status');
    expect(notice).toHaveTextContent(/Too many sign-in attempts\. For safety, sign-in is paused for this email and device\. Try again in 0:03\./i);

    // Submit button is disabled and has paused label
    expect(screen.getByRole('button', { name: /sign in \(paused\)/i })).toBeDisabled();

    // Demo cards remain enabled during pause!
    expect(demoCard).toBeEnabled();

    // Advance clock by 1 second -> countdown updates to 0:02
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(notice).toHaveTextContent(/Try again in 0:02\./i);

    // Advance clock by another 2 seconds -> countdown expires
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    // Notice is gone, submit button re-enabled as "Sign in"
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeEnabled();

    vi.useRealTimers();
  });
});
