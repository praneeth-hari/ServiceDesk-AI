import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';

// Drafts and tokens live in sessionStorage; keep tests isolated from each other.
afterEach(() => {
  sessionStorage.clear();
});
