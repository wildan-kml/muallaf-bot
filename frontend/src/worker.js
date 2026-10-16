const MAX_API_BODY_BYTES = 65_536;
const HUMAN_COOKIE = 'muallaf_human';
const HUMAN_SESSION_SECONDS = 60 * 60;

const SECURITY_HEADERS = {
  'Content-Security-Policy': "default-src 'self'; base-uri 'self'; connect-src 'self' https://challenges.cloudflare.com; font-src 'self'; form-action 'self'; frame-ancestors 'none'; frame-src 'self' https://challenges.cloudflare.com; img-src 'self' data:; object-src 'none'; script-src 'self' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; upgrade-insecure-requests",
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
};

function jsonResponse(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...SECURITY_HEADERS, ...extraHeaders },
  });
}

function base64Url(bytes) {
  let binary = '';
  for (const byte of new Uint8Array(bytes)) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function hmac(value, secret) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return base64Url(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value)));
}

function safeEqual(left, right) {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return difference === 0;
}

async function createHumanCookie(secret) {
  const expiresAt = Math.floor(Date.now() / 1000) + HUMAN_SESSION_SECONDS;
  const nonce = base64Url(crypto.getRandomValues(new Uint8Array(18)));
  const payload = `${expiresAt}.${nonce}`;
  return `${payload}.${await hmac(payload, secret)}`;
}

async function hasValidHumanCookie(request, secret) {
  if (!secret) return false;
  const cookieHeader = request.headers.get('cookie') || '';
  const cookie = cookieHeader.split(';').map((item) => item.trim()).find((item) => item.startsWith(`${HUMAN_COOKIE}=`));
  if (!cookie) return false;
  const value = cookie.slice(HUMAN_COOKIE.length + 1);
  const [expiresAt, nonce, signature] = value.split('.');
  if (!expiresAt || !nonce || !signature || Number(expiresAt) <= Math.floor(Date.now() / 1000)) return false;
  return safeEqual(signature, await hmac(`${expiresAt}.${nonce}`, secret));
}

async function verifyTurnstile(request, env) {
  if (!env.TURNSTILE_SECRET_KEY || !env.HUMAN_SESSION_SECRET || !env.TURNSTILE_SITE_KEY) {
    return jsonResponse({ detail: 'Verifikasi keamanan belum dikonfigurasi oleh pengelola.' }, 503);
  }
  const body = await readJsonBody(request);
  const token = typeof body?.token === 'string' ? body.token : '';
  if (!token || token.length > 2048) return jsonResponse({ detail: 'Verifikasi keamanan tidak valid.' }, 400);
  const form = new URLSearchParams({ secret: env.TURNSTILE_SECRET_KEY, response: token });
  const clientIp = request.headers.get('cf-connecting-ip');
  if (clientIp) form.set('remoteip', clientIp);
  const verification = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  });
  const result = await verification.json().catch(() => ({}));
  if (!result.success || (env.FRONTEND_HOST && result.hostname !== env.FRONTEND_HOST)) {
    return jsonResponse({ detail: 'Verifikasi keamanan gagal. Silakan coba kembali.' }, 403);
  }
  const cookie = await createHumanCookie(env.HUMAN_SESSION_SECRET);
  return jsonResponse(
    { verified: true, expires_in: HUMAN_SESSION_SECONDS },
    200,
    { 'Set-Cookie': `${HUMAN_COOKIE}=${cookie}; Max-Age=${HUMAN_SESSION_SECONDS}; Path=/; HttpOnly; Secure; SameSite=Strict` },
  );
}

async function readJsonBody(request) {
  const buffer = await readBodyLimited(request);
  return JSON.parse(new TextDecoder().decode(buffer) || '{}');
}

async function readBodyLimited(request) {
  const contentLength = Number(request.headers.get('content-length') || 0);
  if (contentLength > MAX_API_BODY_BYTES) throw new Error('BODY_TOO_LARGE');
  if (!request.body) return new ArrayBuffer(0);
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_API_BODY_BYTES) {
      await reader.cancel();
      throw new Error('BODY_TOO_LARGE');
    }
    chunks.push(value);
  }
  const combined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return combined.buffer;
}

async function requestKey(request) {
  const authorization = request.headers.get('authorization');
  if (authorization) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(authorization));
    return `account:${base64Url(digest)}`;
  }
  return `network:${request.headers.get('cf-connecting-ip') || 'unknown'}`;
}

async function enforceRateLimits(request, env, path) {
  const globalResult = await env.GLOBAL_RATE_LIMITER.limit({ key: 'muallaf-bot-api' });
  if (!globalResult.success) return jsonResponse({ detail: 'Layanan sedang sibuk. Coba lagi sebentar.' }, 429, { 'Retry-After': '60' });
  if (path === '/api/chat') {
    const result = await env.CHAT_RATE_LIMITER.limit({ key: await requestKey(request) });
    if (!result.success) return jsonResponse({ detail: 'Batas pertanyaan per menit telah tercapai.' }, 429, { 'Retry-After': '60' });
  }
  if (path === '/api/auth/login' || path === '/api/auth/register') {
    const result = await env.AUTH_RATE_LIMITER.limit({ key: `${path}:${request.headers.get('cf-connecting-ip') || 'unknown'}` });
    if (!result.success) return jsonResponse({ detail: 'Terlalu banyak percobaan. Coba lagi satu menit.' }, 429, { 'Retry-After': '60' });
  }
  return null;
}

async function proxyApi(request, env, path) {
  if (!env.ORIGIN_SHARED_SECRET || !env.MODAL_PROXY_TOKEN_ID || !env.MODAL_PROXY_TOKEN_SECRET || !env.API_ORIGIN) {
    return jsonResponse({ detail: 'Jalur API belum dikonfigurasi.' }, 503);
  }
  const limited = await enforceRateLimits(request, env, path);
  if (limited) return limited;
  const authorization = request.headers.get('authorization');
  const needsHuman = path === '/api/auth/register' || (path === '/api/chat' && !authorization);
  if (needsHuman && !(await hasValidHumanCookie(request, env.HUMAN_SESSION_SECRET))) {
    return jsonResponse({ detail: 'Selesaikan verifikasi keamanan terlebih dahulu.' }, 403);
  }
  const target = new URL(request.url);
  const origin = new URL(env.API_ORIGIN);
  target.protocol = origin.protocol;
  target.host = origin.host;
  const headers = new Headers(request.headers);
  headers.delete('cookie');
  headers.delete('host');
  headers.delete('x-origin-verify');
  headers.delete('x-muallaf-client-ip');
  headers.set('x-origin-verify', env.ORIGIN_SHARED_SECRET);
  headers.set('x-muallaf-client-ip', request.headers.get('cf-connecting-ip') || 'unknown');
  headers.set('modal-key', env.MODAL_PROXY_TOKEN_ID);
  headers.set('modal-secret', env.MODAL_PROXY_TOKEN_SECRET);
  let body;
  if (!['GET', 'HEAD'].includes(request.method)) {
    try {
      body = await readBodyLimited(request);
    } catch (error) {
      if (error?.message === 'BODY_TOO_LARGE') return jsonResponse({ detail: 'Ukuran permintaan terlalu besar.' }, 413);
      throw error;
    }
  }
  const response = await fetch(target, { method: request.method, headers, body, redirect: 'manual' });
  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete('set-cookie');
  responseHeaders.set('Cache-Control', 'no-store');
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) responseHeaders.set(name, value);
  const isInlinePdf = path.startsWith('/api/documents/files/')
    && responseHeaders.get('Content-Type')?.toLowerCase().startsWith('application/pdf');
  if (isInlinePdf) {
    responseHeaders.set('Content-Security-Policy', "frame-ancestors 'self'");
    responseHeaders.set('X-Frame-Options', 'SAMEORIGIN');
  }
  return new Response(response.body, { status: response.status, headers: responseHeaders });
}

async function handleRequest(request, env) {
  const url = new URL(request.url);
  if (url.pathname === '/api/security/config' && request.method === 'GET') {
    return jsonResponse({ enabled: Boolean(env.TURNSTILE_SITE_KEY), site_key: env.TURNSTILE_SITE_KEY || null });
  }
  if (url.pathname === '/api/security/status' && request.method === 'GET') {
    return jsonResponse({ verified: await hasValidHumanCookie(request, env.HUMAN_SESSION_SECRET) });
  }
  if (url.pathname === '/api/security/verify' && request.method === 'POST') {
    try {
      return await verifyTurnstile(request, env);
    } catch (error) {
      if (error?.message === 'BODY_TOO_LARGE') return jsonResponse({ detail: 'Ukuran permintaan terlalu besar.' }, 413);
      return jsonResponse({ detail: 'Permintaan verifikasi tidak valid.' }, 400);
    }
  }
  if (url.pathname.startsWith('/api/')) return proxyApi(request, env, url.pathname);
  const response = await env.ASSETS.fetch(request);
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) headers.set(name, value);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

export default {
  async fetch(request, env) {
    try {
      return await handleRequest(request, env);
    } catch {
      return jsonResponse({ detail: 'Layanan sementara tidak tersedia.' }, 503);
    }
  },
};
