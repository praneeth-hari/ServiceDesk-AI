import { ApiError } from '../api/client';

/**
 * Maps raw API errors, status codes, or network exceptions into
 * user-friendly, plain English sentences.
 */
export function getFriendlyErrorMessage(
  err: unknown,
  fallback = 'An unexpected error occurred. Please try again.'
): string {
  if (!err) return fallback;

  // 1. If err is an ApiError instance
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return 'Your sign-in has expired. Please sign in again.';
    }
    if (err.status === 403) {
      return 'You do not have permission to perform this action.';
    }
    if (err.status === 404) {
      return 'The requested resource was not found.';
    }
    if (err.status === 409) {
      return err.message && !err.message.startsWith('HTTP ')
        ? err.message
        : 'A conflicting item already exists.';
    }
    if (err.status === 422) {
      return err.message && !err.message.startsWith('HTTP ')
        ? err.message
        : 'Please check the entered fields and try again.';
    }
    if (err.status >= 500 && err.status < 600) {
      return 'A server problem occurred. Please try again.';
    }
    if (err.message && !err.message.startsWith('HTTP ')) {
      return err.message;
    }
  }

  // 2. String representation inspection
  const raw =
    typeof err === 'string'
      ? err
      : err instanceof Error
        ? err.message
        : String(err);

  // Network or fetch connection failures
  if (/failed to fetch|network\s?error|load failed/i.test(raw)) {
    return 'Network error. Please check your connection and try again.';
  }

  // Generic "Failed to load ..."
  if (/^failed to load/i.test(raw)) {
    return 'A server problem occurred. Please try again.';
  }

  // Check embedded status codes like "HTTP 500: ...", "409 Conflict", etc.
  const statusMatch = raw.match(/\b(401|403|404|409|422|5\d\d)\b/);
  if (statusMatch) {
    const code = parseInt(statusMatch[1], 10);
    if (code === 401) return 'Your sign-in has expired. Please sign in again.';
    if (code === 403) return 'You do not have permission to perform this action.';
    if (code === 404) return 'The requested resource was not found.';
    if (code === 409) {
      return raw.includes('already exists')
        ? raw
        : 'A conflicting item already exists.';
    }
    if (code === 422) return 'Please check the entered fields and try again.';
    if (code >= 500 && code < 600) return 'A server problem occurred. Please try again.';
  }

  // If raw is already a clean user-facing sentence without HTTP codes
  if (raw && !raw.startsWith('HTTP ') && !raw.includes('Internal Server Error')) {
    return raw;
  }

  return fallback;
}

