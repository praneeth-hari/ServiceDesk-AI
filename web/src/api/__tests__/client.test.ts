import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, ApiError } from '../client';

describe('api client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('sends the Authorization header when token is stored', async () => {
    sessionStorage.setItem('access_token', 'test-token-123');

    let capturedHeaders: Headers | undefined;
    globalThis.fetch = vi.fn().mockImplementation((_url, init) => {
      capturedHeaders = new Headers(init?.headers);
      return Promise.resolve(
        new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });

    const result = await apiFetch<{ status: string }>('/health');

    expect(result).toEqual({ status: 'ok' });
    expect(capturedHeaders?.get('Authorization')).toBe('Bearer test-token-123');
  });

  it('handles 401: clears session and throws ApiError', async () => {
    sessionStorage.setItem('access_token', 'expired-token');
    sessionStorage.setItem('user', JSON.stringify({ email: 'test@example.com' }));

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ error: { message: 'Invalid authentication token' } }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }
      )
    );

    await expect(apiFetch('/users/me')).rejects.toThrow(ApiError);

    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('user')).toBeNull();
  });

  it('parses structured API errors from JSON responses', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ error: { message: 'Entity not found' } }),
        {
          status: 404,
          statusText: 'Not Found',
          headers: { 'Content-Type': 'application/json' },
        }
      )
    );

    try {
      await apiFetch('/tickets/999');
      expect.fail('Should have thrown an ApiError');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.message).toBe('Entity not found');
    }
  });
});
