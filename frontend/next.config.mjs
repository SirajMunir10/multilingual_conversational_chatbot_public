// XO frontend (Next.js). Exported as static files, so the existing nginx/Docker and Vercel setups keep working:
// the widget runs entirely in the browser (microphone, audio, storage) and talks to the FastAPI backend.
const isDev = process.env.NODE_ENV === 'development'

// Backend locations are read at build time. The old Vite names are still accepted so existing
// deployments (e.g. Vercel's VITE_API_WS_BASE) keep working until they are renamed.
for (const name of ['API_BASE', 'API_WS_BASE']) {
  if (!process.env[`NEXT_PUBLIC_${name}`] && process.env[`VITE_${name}`]) {
    process.env[`NEXT_PUBLIC_${name}`] = process.env[`VITE_${name}`]
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
  reactStrictMode: true,
  // Local development: /api is forwarded to the backend (production uses nginx or Vercel for this).
  ...(isDev && {
    async rewrites() {
      return [{ source: '/api/:path*', destination: `${process.env.DEV_API_TARGET || 'http://127.0.0.1:8000'}/api/:path*` }]
    }
  })
}

export default nextConfig
