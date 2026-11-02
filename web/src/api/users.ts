import { apiFetch } from './client';
import type { User } from './types';

export async function listUsers(skip = 0, limit = 100): Promise<User[]> {
  return apiFetch<User[]>(`/users?skip=${skip}&limit=${limit}`);
}

export async function listAgents(): Promise<User[]> {
  const users = await listUsers(0, 100);
  return users.filter((u) => u.role === 'agent' && u.is_active);
}

