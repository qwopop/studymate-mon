import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'

// End-to-end tests drive the real app: a FastAPI backend (demo SDU data, throw-away SQLite file) and the Vite dev server.
//   npx playwright install chromium     (once)
//   npm run test:e2e
// PYTHON picks the interpreter (default "python"); CHROMIUM_PATH points at an already installed Chromium.
const python = process.env.PYTHON || 'python'
const db = path.join(os.tmpdir(), `studymate-e2e-${process.pid}.db`)

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'off',
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --port 8000`,
      cwd: '../backend',
      url: 'http://localhost:8000/health',
      // Never touch the real university portal from a test: portal login is off and its address is a dead local port
      env: { ENABLE_DEMO_MODE: '1', SQLITE_PATH: db, STUDYMATE_SKIP_DOTENV: '1', ENABLE_PORTAL_LOGIN: '0', SDU_PORTAL_ORIGIN: 'http://127.0.0.1:9' },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
