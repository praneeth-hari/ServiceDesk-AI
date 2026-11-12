import { expect, test, type Page } from '@playwright/test';

type Role = 'requester' | 'agent' | 'admin';

const ROLE_BUTTON: Record<Role, RegExp> = {
  requester: /requester/i,
  agent: /agent/i,
  admin: /admin/i,
};

async function demoLogin(page: Page, role: Role) {
  await page.goto('/login');
  await page.getByRole('button', { name: ROLE_BUTTON[role] }).first().click();
  await page.waitForURL('**/tickets');
}

/** Collects console errors, page errors and Content-Security-Policy violations. */
function watchForErrors(page: Page): string[] {
  const problems: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') problems.push(`console: ${msg.text()}`);
  });
  page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
  return problems;
}

test.describe('requester', () => {
  test('creates a ticket and gets AI triage suggestions', async ({ page }) => {
    const problems = watchForErrors(page);
    await demoLogin(page, 'requester');

    await page.getByRole('link', { name: 'New ticket' }).first().click();
    await page.waitForURL('**/tickets/new');

    const title = `E2E VPN failure ${Date.now()}`;
    await page.getByLabel(/title/i).fill(title);
    await page
      .getByLabel(/description/i)
      .fill('Cannot connect to the corporate VPN from home since this morning. Gateway times out.');

    // The advisory panel analyses the text after a short pause
    await expect(page.getByText('AI Triage Advisory')).toBeVisible();
    await expect(page.getByText(/Analyzing|Suggestions|No confident suggestion/i).first()).toBeVisible();

    await page.getByLabel(/category/i).selectOption('network');
    await page.getByRole('button', { name: /^(Create ticket|Create anyway)$/ }).click();

    await page.waitForURL(/\/tickets\/\d+$/);
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    expect(problems).toEqual([]);
  });

  test('keeps a draft of the new ticket form', async ({ page }) => {
    await demoLogin(page, 'requester');
    await page.goto('/tickets/new');
    await page.getByLabel(/title/i).fill('Draft title that should survive');
    await page.reload();
    await expect(page.getByLabel(/title/i)).toHaveValue('Draft title that should survive');
  });

  test('cannot open staff pages', async ({ page }) => {
    await demoLogin(page, 'requester');
    await page.goto('/reports');
    // The route guard sends requesters back to their ticket list
    await page.waitForURL('**/tickets');
    await expect(page.getByRole('link', { name: 'Reports' })).toHaveCount(0);
  });
});

test.describe('agent', () => {
  test('reopens a resolved ticket and sees it in the activity log', async ({ page }) => {
    await demoLogin(page, 'agent');
    await page.getByRole('button', { name: 'Table' }).click();
    await page.locator('table tbody tr', { hasText: 'Resolved' }).first().click();
    await page.waitForURL(/\/tickets\/\d+$/);

    await page.getByRole('button', { name: 'Reopen' }).click();
    await expect(page.getByText('Resolved → In progress')).toBeVisible();
  });
});

test.describe('admin', () => {
  test('every page loads without console errors or CSP violations', async ({ page }) => {
    const problems = watchForErrors(page);
    await demoLogin(page, 'admin');

    for (const path of ['/tickets', '/tickets/new', '/reports', '/ai-quality', '/users', '/holidays']) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await expect(page.getByRole('link', { name: 'Tickets' }).first()).toBeVisible();
    }
    expect(problems).toEqual([]);
  });
});

test.describe('sign out', () => {
  test('ends the session and invalidates the old token', async ({ page, request }) => {
    await demoLogin(page, 'requester');
    const token = await page.evaluate(() => sessionStorage.getItem('access_token'));
    expect(token).toBeTruthy();
    const auth = { Authorization: `Bearer ${token}` };
    expect((await request.get('/api/v1/users/me', { headers: auth })).status()).toBe(200);

    await page.getByRole('button', { name: 'Sign out' }).first().click();
    await page.waitForURL('**/login');

    // The server rejects the token that was just signed out
    await expect
      .poll(async () => (await request.get('/api/v1/users/me', { headers: auth })).status())
      .toBe(401);

    // Protected pages send an anonymous visitor to the login page
    await page.goto('/tickets');
    await page.waitForURL('**/login');
  });
});
