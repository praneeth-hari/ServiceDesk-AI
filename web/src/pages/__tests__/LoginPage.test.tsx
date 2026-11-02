import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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
    const submitBtn = screen.getByRole('button', { name: /sign in/i });

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
    const submitBtn = screen.getByRole('button', { name: /sign in/i });

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
    const submitBtn = screen.getByRole('button', { name: /sign in/i });

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
    const submitBtn = screen.getByRole('button', { name: /sign in/i });

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
});
