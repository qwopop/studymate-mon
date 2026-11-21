import '@testing-library/jest-dom/vitest'

// recharts measures its container with ResizeObserver, which jsdom does not have
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
