# Runway &bull; ServiceDesk-AI Web Application

React + TypeScript + Vite + Tailwind CSS frontend for the ServiceDesk-AI platform.

## Features

- **Authentication**: JWT-based sign-in with session isolation and role awareness (`requester`, `agent`, `admin`).
- **Design Tokens**: "Runway" aesthetic with warm paper backgrounds (`#FBF8F3`, `#F2EDE3`), serif typography (`Source Serif 4`), and teal accents (`#0F766E`).
- **Routing**: Client-side navigation via `react-router-dom` with `ProtectedRoute` and `RoleRoute` helpers.
- **Proxy**: Development server proxies `/api` requests directly to FastAPI backend on port 8000.

## Development

```powershell
# Install dependencies
npm install

# Start Vite dev server on port 5173
npm run dev

# Run test suite (Vitest + React Testing Library)
npm test

# Run ESLint
npm run lint

# Build production bundle
npm run build
```
