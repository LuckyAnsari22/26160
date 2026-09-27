// Links and names used across the page.
//
// The landing page and the dashboard are served by the same FastAPI app
// (landing at "/", dashboard at "/app/"), so in production the dashboard link
// is a plain same-origin path. Only `npm run dev` on its own (Vite on :5173,
// no FastAPI) needs to point elsewhere: at a locally running backend by
// default, or VITE_DEV_DASHBOARD_URL if set.
export const DASHBOARD_URL = import.meta.env.DEV
  ? import.meta.env.VITE_DEV_DASHBOARD_URL || 'http://localhost:8000/app/'
  : '/app/';

// Public repo link. The default is the real repo, so a build from a clean
// clone (e.g. Railway, where untracked files don't exist) never shows a
// placeholder; override with VITE_GITHUB_URL.
export const GITHUB_URL = import.meta.env.VITE_GITHUB_URL || 'https://github.com/LuckyAnsari22/26160';
export const TEAM_NAME = import.meta.env.VITE_TEAM_NAME || '{TEAM_NAME}';
