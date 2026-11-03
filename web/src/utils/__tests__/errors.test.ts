import { describe, it, expect } from 'vitest';
import { getFriendlyErrorMessage } from '../errors';
import { ApiError } from '../../api/client';

describe('getFriendlyErrorMessage', () => {
  it('maps 401 status to sign-in expired sentence', () => {
    const err = new ApiError(401, 'HTTP 401: Unauthorized');
    expect(getFriendlyErrorMessage(err)).toBe('Your sign-in has expired. Please sign in again.');
  });

  it('maps 403 status to not allowed sentence', () => {
    const err = new ApiError(403, 'Forbidden');
    expect(getFriendlyErrorMessage(err)).toBe('You do not have permission to perform this action.');
  });

  it('maps 404 status to not found sentence', () => {
    const err = new ApiError(404, 'Not Found');
    expect(getFriendlyErrorMessage(err)).toBe('The requested resource was not found.');
  });

  it('maps 409 status to conflict message', () => {
    const err = new ApiError(409, 'A holiday on 2026-01-26 already exists');
    expect(getFriendlyErrorMessage(err)).toBe('A holiday on 2026-01-26 already exists');

    const errGeneric = new ApiError(409, 'HTTP 409: Conflict');
    expect(getFriendlyErrorMessage(errGeneric)).toBe('A conflicting item already exists.');
  });

  it('maps 422 status to check fields message', () => {
    const err = new ApiError(422, 'HTTP 422: Unprocessable Entity');
    expect(getFriendlyErrorMessage(err)).toBe('Please check the entered fields and try again.');

    const errCustom = new ApiError(422, 'Name must be at least 1 character');
    expect(getFriendlyErrorMessage(errCustom)).toBe('Name must be at least 1 character');
  });

  it('maps 5xx status to server problem sentence', () => {
    const err = new ApiError(500, 'HTTP 500: Internal Server Error');
    expect(getFriendlyErrorMessage(err)).toBe('A server problem occurred. Please try again.');

    const err502 = new ApiError(502, 'HTTP 502: Bad Gateway');
    expect(getFriendlyErrorMessage(err502)).toBe('A server problem occurred. Please try again.');
  });

  it('maps network errors to connection sentence', () => {
    expect(getFriendlyErrorMessage(new TypeError('Failed to fetch'))).toBe(
      'Network error. Please check your connection and try again.'
    );
    expect(getFriendlyErrorMessage('NetworkError when attempting to fetch resource.')).toBe(
      'Network error. Please check your connection and try again.'
    );
  });

  it('maps raw string messages containing HTTP codes', () => {
    expect(getFriendlyErrorMessage('HTTP 500: Internal Server Error')).toBe(
      'A server problem occurred. Please try again.'
    );
    expect(getFriendlyErrorMessage('Failed to load report data')).toBe(
      'A server problem occurred. Please try again.'
    );
  });

  it('falls back to custom fallback or default message', () => {
    expect(getFriendlyErrorMessage(null, 'Custom fallback')).toBe('Custom fallback');
    expect(getFriendlyErrorMessage(undefined)).toBe('An unexpected error occurred. Please try again.');
  });
});

