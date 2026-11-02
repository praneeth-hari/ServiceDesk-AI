import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { RoleRoute } from '../RoleRoute';
import { AuthProvider } from '../../context/AuthContext';

describe('RoleRoute', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('blocks a requester from /reports and redirects to fallback', async () => {
    sessionStorage.setItem('access_token', 'valid-token');
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 3,
        email: 'requester@example.com',
        full_name: 'Ravi Requester',
        role: 'requester',
        is_active: true,
        created_at: '2026-10-25T11:00:00',
      })
    );

    render(
      <MemoryRouter initialEntries={['/reports']}>
        <AuthProvider>
          <Routes>
            <Route path="/tickets" element={<div>Tickets Page (Fallback)</div>} />
            <Route element={<RoleRoute staffOnly fallbackPath="/tickets" />}>
              <Route path="/reports" element={<div>Confidential Reports</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    expect(await screen.findByText('Tickets Page (Fallback)')).toBeInTheDocument();
    expect(screen.queryByText('Confidential Reports')).not.toBeInTheDocument();
  });

  it('allows staff (agent/admin) to access /reports', async () => {
    sessionStorage.setItem('access_token', 'valid-token');
    sessionStorage.setItem(
      'user',
      JSON.stringify({
        id: 2,
        email: 'agent@example.com',
        full_name: 'Asha Agent',
        role: 'agent',
        is_active: true,
        created_at: '2026-10-25T11:00:00',
      })
    );

    render(
      <MemoryRouter initialEntries={['/reports']}>
        <AuthProvider>
          <Routes>
            <Route path="/tickets" element={<div>Tickets Page (Fallback)</div>} />
            <Route element={<RoleRoute staffOnly fallbackPath="/tickets" />}>
              <Route path="/reports" element={<div>Confidential Reports</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    );

    expect(await screen.findByText('Confidential Reports')).toBeInTheDocument();
  });
});

