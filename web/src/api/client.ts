import { ApiErrorResponse, TriageFeedbackRead, AIQualityReportResponse } from './types';

export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

const BASE_URL = '/api/v1';

export interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const url = endpoint.startsWith('/api')
    ? endpoint
    : `${BASE_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;

  const headers = new Headers(options.headers || {});

  if (!options.skipAuth) {
    const token = typeof window !== 'undefined' ? sessionStorage.getItem('access_token') : null;
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  if (options.body && typeof options.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
    let errorData: unknown;

    try {
      const json = await response.json();
      errorData = json;
      const apiErr = json as ApiErrorResponse;
      if (apiErr?.error?.message) {
        errorMessage = apiErr.error.message;
      } else if (typeof (json as { message?: string }).message === 'string') {
        errorMessage = (json as { message: string }).message;
      }
    } catch {
      // Body was not JSON
    }

    if (response.status === 401) {
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('user');
        if (window.location && window.location.pathname !== '/login') {
          try {
            window.location.href = '/login';
          } catch {
            // Ignored in test environments like JSDOM where navigation isn't implemented
          }
        }
      }
    }

    throw new ApiError(response.status, errorMessage, errorData);
  }

  if (response.status === 204) {
    return null as T;
  }

  return response.json() as Promise<T>;
}

export async function getTicketTriageFeedback(ticketId: number): Promise<TriageFeedbackRead> {
  return apiFetch<TriageFeedbackRead>(`/tickets/${ticketId}/triage-feedback`);
}

export async function confirmTriageFeedback(ticketId: number): Promise<TriageFeedbackRead> {
  return apiFetch<TriageFeedbackRead>(`/tickets/${ticketId}/triage-feedback/confirm`, {
    method: 'POST',
  });
}

export async function getAIQualityReport(days?: number): Promise<AIQualityReportResponse> {
  const query = days !== undefined ? `?days=${days}` : '';
  return apiFetch<AIQualityReportResponse>(`/reports/ai-quality${query}`);
}
