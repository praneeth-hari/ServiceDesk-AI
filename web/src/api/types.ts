export type UserRole = 'requester' | 'agent' | 'admin';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface ApiErrorDetail {
  message: string;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

