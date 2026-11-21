import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

// Component tests (*.spec.jsx) run in jsdom. The pure-logic tests (*.test.js) keep using node:test.
export default mergeConfig(viteConfig, defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.spec.{js,jsx}'],
    setupFiles: ['./src/test-setup.js'],
    css: false,
  },
}))
