import { expect, test } from '@playwright/test'

// A student with demo SDU data, signed in the way the app stores it after login
async function signIn(page, request) {
  const session = await (await request.post('http://localhost:8000/api/sdu/demo-connect', { data: {} })).json()
  await page.goto('/')
  await page.evaluate(s => localStorage.setItem('session', JSON.stringify(s)), session)
  await page.goto('/')
}

test('student can sign in with the login form', async ({ page, request }) => {
  // An e-mail login is a local account login. (A student number would go to the real SDU portal, never in tests.)
  const email = `e2e-${Date.now()}@univ.edu`
  const reg = await request.post('http://localhost:8000/api/auth/register', {
    data: { name: 'E2E Student', identifier: email, email, password: 'e2e-password-1', role: 'student' } })
  expect(reg.ok()).toBeTruthy()
  await page.goto('/')
  await page.getByLabel(/Student number, teacher username, or email/).fill(email)
  await page.locator('input[type="password"]').first().fill('e2e-password-1')
  await page.getByRole('button', { name: 'Sign in →' }).click()
  await expect(page.getByRole('button', { name: 'Monitoring' }).first()).toBeVisible()
})

test('Monitoring tab shows safe-to-skip, AI risk, simulation and alerts', async ({ page, request }) => {
  await signIn(page, request)
  await page.getByRole('button', { name: 'Monitoring' }).first().click()
  await expect(page.getByRole('heading', { name: 'Safe to skip' })).toBeVisible()
  await expect(page.getByText(/Absence limit: \d+\. You have: \d+\. Remaining: \d+\./).first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'AI risk assessment' })).toBeVisible()
  await expect(page.getByText(/^Your risk is \d+%/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Alerts', exact: true })).toBeVisible()

  // moving a slider asks the backend again and the answer is shown
  const answer = page.waitForResponse(r => r.url().endsWith('/api/simulate') && r.request().method() === 'POST')
  await page.getByLabel(/Lectures to skip/).fill('6')
  expect((await answer).status()).toBe(200)
  await expect(page.getByText(/New predicted GPA: [\d.]+\./)).toBeVisible()
})

test('Sync button refreshes the data and updates "Last synced"', async ({ page, request }) => {
  await signIn(page, request)
  await page.getByRole('button', { name: 'Monitoring' }).first().click()
  const sync = page.waitForResponse(r => r.url().endsWith('/api/sdu/sync') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Sync with SDU' }).click()
  expect((await sync).status()).toBe(200)
  await expect(page.getByText(/Last synced: (just now|1 min ago)/)).toBeVisible()
})

test('Overview shows the AI predicted GPA widget and links to Monitoring', async ({ page, request }) => {
  await signIn(page, request)
  await expect(page.getByText('Predicted GPA (AI)')).toBeVisible()
  await page.getByRole('button', { name: /Open Monitoring/ }).click()
  await expect(page.getByRole('heading', { name: 'Safe to skip' })).toBeVisible()
})
