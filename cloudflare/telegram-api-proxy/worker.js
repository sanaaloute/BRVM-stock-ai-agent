/**
 * Cloudflare Worker: reverse proxy for the Telegram Bot API.
 *
 * Purpose: run the BRVM bot on a host from which api.telegram.org is
 * unreachable (e.g. mainland China) WITHOUT a system-wide VPN. The bot points
 * at this worker (TELEGRAM_BASE_URL) and all Bot API calls + file downloads
 * flow through Cloudflare's network instead of a direct connection.
 *
 * Deploy:
 *   cd cloudflare/telegram-api-proxy
 *   npx wrangler deploy            # or paste this file in the dashboard editor
 *
 * Then set in .env:
 *   TELEGRAM_BASE_URL=https://telegram-api-proxy.<your-subdomain>.workers.dev
 *
 * Security: this is NOT an open relay. Only Telegram Bot API path shapes are
 * forwarded (/bot<token>/<method> and /file/bot<token>/<path>); everything
 * else gets 404. Your bot token is never stored here — it only passes through
 * in request paths. Keep the worker URL unguessable (rename the worker) and
 * rotate the token via @BotFather if the URL ever leaks.
 */

const TELEGRAM_HOST = "api.telegram.org";

// Bot API calls:  /bot<token>/<method>          e.g. /bot123:abc/getUpdates
// File downloads: /file/bot<token>/<file_path>  e.g. /file/bot123:abc/voice/file_1.oga
const ALLOWED_PATH = /^\/(file\/)?bot[^/]+\/.+/;

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (!ALLOWED_PATH.test(url.pathname)) {
      return new Response("not found", { status: 404 });
    }

    url.hostname = TELEGRAM_HOST;
    url.protocol = "https:";
    url.port = "";

    const headers = new Headers(request.headers);
    headers.delete("host");
    // Cloudflare sets cf-* / x-forwarded-* headers; harmless to Telegram, but
    // strip anything that could confuse the upstream.
    headers.delete("cf-connecting-ip");
    headers.delete("cf-ray");

    const upstream = new Request(url.toString(), {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "follow",
    });
    return fetch(upstream);
  },
};
