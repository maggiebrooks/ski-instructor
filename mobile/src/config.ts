/**
 * Backend & web app endpoints for the recorder.
 *
 * Local dev:
 *   - iOS Simulator: `http://localhost:8000` works because the simulator shares
 *     the host network namespace.
 *   - Physical iPhone via Expo Go: set DEV_URL to your dev Mac's LAN IP
 *     (`ipconfig getifaddr en0` on macOS). Phone and Mac must be on the same Wi‑Fi.
 *
 * Production: PROD_URL is the Render web service (API at same host under /api).
 *
 * NOTE: this file is the only place to change those URLs. Both screens import
 * from here.
 */

// DEV_URL: update this when your local IP changes (development only)
// PROD_URL: stable Render URL — never changes
const PROD_URL = 'https://ski-ai-web.onrender.com';
const DEV_URL = 'http://10.0.0.68:8000';

export const API_BASE_URL = __DEV__ ? DEV_URL : PROD_URL;
export const WEB_APP_URL = __DEV__ ? 'http://localhost:5173' : PROD_URL;
