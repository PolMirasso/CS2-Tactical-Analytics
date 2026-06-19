# CS2 Tactical Analytics — Frontend

React + TypeScript + Vite SPA for the FastAPI backend in `../backend`.

## Stack

- **Vite + React 18 + TypeScript**
- **TanStack Query** — server state, caching, and live polling of HLTV download jobs
- **React Router** — routing with a protected app shell
- **react-i18next** — translations (English + Spanish, language switcher in the navbar)

## Getting started

```bash
cd frontend
cp .env.example .env.local   # adjust VITE_API_BASE_URL if the backend isn't on :8000
npm install
npm run dev                  # http://localhost:5173
```

The backend already allows `http://localhost:5173` via CORS. Log in with the
bootstrap admin (see `backend/.env`) or register a new account.

## Scripts

- `npm run dev` — dev server with HMR
- `npm run build` — type-check (`tsc -b`) + production build
- `npm run preview` — serve the production build

## Folder structure

```
frontend/
├── index.html
├── vite.config.ts            # @ -> src alias, dev server on :5173
├── tsconfig*.json
└── src/
    ├── main.tsx              # entrypoint (mounts <App/>, loads i18n + styles)
    ├── app/
    │   ├── App.tsx           # providers: QueryClient → Auth → Router
    │   └── router.tsx        # route table (public + protected shell)
    ├── lib/
    │   ├── apiClient.ts      # typed fetch wrapper, JWT header, error normalisation
    │   ├── queryClient.ts    # TanStack Query client config
    │   └── format.ts         # bytes / date helpers
    ├── types/
    │   └── api.ts            # TS mirror of backend pydantic schemas + enums
    ├── i18n/
    │   ├── index.ts          # i18next init
    │   └── locales/{en,es}/common.json
    ├── components/           # shared UI (Layout, NavBar, ProtectedRoute, …)
    └── features/             # one folder per domain, each with api.ts + hooks.ts + pages
        ├── auth/             # login, register, AuthContext (token in localStorage)
        ├── demos/            # list, upload, detail, re-parse, delete
        ├── hltv/             # team search, start download, jobs (live polling)
        ├── groups/           # groups, invitations
        └── maps/             # map/zone definitions + SVG zone scatter
```

## Conventions for growing this

- **One feature = one folder** under `features/`, owning its `api.ts` (endpoint
  calls), `hooks.ts` (TanStack Query wrappers), and components/pages.
- **All HTTP goes through `lib/apiClient.ts`** — never call `fetch` from a component.
- **No hardcoded UI strings** — add keys to `i18n/locales/*/common.json` and use
  `t('…')`. Split `common.json` into per-feature namespaces when it grows.
- `types/api.ts` is hand-kept in sync with the backend; a later step can generate
  it from the backend's OpenAPI schema (`/openapi.json`).

## Next steps (not in this scaffold)

- Real tactical map view: radar image per map + world→pixel transform, utility
  heatmaps over `ZoneScatter`'s placeholder.
- A backend aggregation endpoint (utility frequency per zone/team/map) to feed it.
- OpenAPI-generated API types and an auth-refresh flow.
```
