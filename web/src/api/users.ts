import { apiFetch } from './client';
import type {
  User,
  UserAdmin,
  UserCreateInput,
  UserListResponse,
  UserRole,
} from './types';

export interface ListUsersFilters {
  q?: string;
  role?: UserRole;
  is_active?: boolean;
}

export async function listUsers(skip = 0, limit = 100): Promise<User[]> {
  return apiFetch<User[]>(`/users?skip=${skip}&limit=${limit}`);
}

export async function listAgents(): Promise<User[]> {
  const users = await listUsers(0, 100);
  return users.filter((u) => u.role === 'agent' && u.is_active);
}

export async function listAdminUsers(filters?: ListUsersFilters): Promise<UserListResponse> {
  const params = new URLSearchParams();
  if (filters?.q) params.set('q', filters.q);
  if (filters?.role) params.set('role', filters.role);
  if (filters?.is_active !== undefined) params.set('is_active', String(filters.is_active));
  const qs = params.toString();
  return apiFetch<UserListResponse>(`/users/admin${qs ? `?${qs}` : ''}`);
}

export async function createAdminUser(data: UserCreateInput): Promise<UserAdmin> {
  return apiFetch<UserAdmin>('/users', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateUserRole(id: number, role: UserRole): Promise<User> {
  return apiFetch<User>(`/users/${id}/role`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
}

export async function updateUserStatus(id: number, is_active: boolean): Promise<User> {
  return apiFetch<User>(`/users/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active }),
  });
}
