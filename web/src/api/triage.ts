import { apiFetch } from './client';
import type { TriageSuggestRequest, TriageSuggestResponse } from './types';

export async function suggestTriage(
  input: TriageSuggestRequest,
  signal?: AbortSignal
): Promise<TriageSuggestResponse> {
  return apiFetch<TriageSuggestResponse>('/triage/suggest', {
    method: 'POST',
    body: JSON.stringify(input),
    signal,
  });
}

