import { httpAdapter } from './http-adapter'
// The local backend is itself a zero-credential fictional sandbox. Never silently substitute fabricated data.
export const dataMode='api' as const
export const api=httpAdapter
