import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthProvider } from '../AuthContext';
import { useAuth } from '../useAuth';
import * as client from '../../api/client';

const cachedUser = {
  id: 1,
  email: 'a@example.com',
  full_name: 'Agent A',
  role: 'agent',
  is_active: true,
  created_at: '2026-10-25T11:00:00',
};

function ShowRole() {
  const { role } = useAuth();
  return <div data-testid="role">{role ?? 'none'}</div>;
}

describe('AuthProvider profile refresh', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.setItem('access_token', 'tok');
    sessionStorage.setItem('user', JSON.stringify(cachedUser));
  });

  it('refreshes a cached profile so a changed role is picked up', async () => {
    vi.spyOn(client, 'apiFetch').mockResolvedValue({ ...cachedUser, role: 'requester' });
    render(
      <AuthProvider>
        <ShowRole />
      </AuthProvider>
    );
    expect(screen.getByTestId('role')).toHaveTextContent('agent');
    await waitFor(() => expect(screen.getByTestId('role')).toHaveTextContent('requester'));
    expect(JSON.parse(sessionStorage.getItem('user')!).role).toBe('requester');
  });

  it('keeps the cached profile when the refresh fails for a non-auth reason', async () => {
    const spy = vi.spyOn(client, 'apiFetch').mockRejectedValue(new TypeError('Failed to fetch'));
    render(
      <AuthProvider>
        <ShowRole />
      </AuthProvider>
    );
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.getByTestId('role')).toHaveTextContent('agent');
  });

  it('signs out when the refresh returns 401', async () => {
    vi.spyOn(client, 'apiFetch').mockRejectedValue(new client.ApiError(401, 'expired'));
    render(
      <AuthProvider>
        <ShowRole />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId('role')).toHaveTextContent('none'));
    expect(sessionStorage.getItem('access_token')).toBeNull();
  });
});

describe('AuthProvider logout', () => {
  it('clears the session and asks the server to invalidate the token', async () => {
    sessionStorage.setItem('access_token', 'tok');
    sessionStorage.setItem('user', JSON.stringify(cachedUser));
    const spy = vi
      .spyOn(client, 'apiFetch')
      .mockImplementation(async (endpoint: string) =>
        (endpoint === '/users/me' ? cachedUser : null) as never
      );

    function LogoutButton() {
      const { logout, role } = useAuth();
      return (
        <button onClick={logout}>
          {role ?? 'signed-out'}
        </button>
      );
    }

    render(
      <AuthProvider>
        <LogoutButton />
      </AuthProvider>
    );
    await waitFor(() => expect(spy).toHaveBeenCalledWith('/users/me'));
    screen.getByRole('button').click();

    await waitFor(() => expect(screen.getByRole('button')).toHaveTextContent('signed-out'));
    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(spy).toHaveBeenCalledWith(
      '/auth/logout',
      expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer tok' } })
    );
  });
});
