import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createHmac, randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';

const ORIGIN = 'https://download.kaan.win';
const COOKIE = '__Host-download-session';
const SESSION_SECONDS = 3600;
const FILES = [
  ['archicad-connector-0.1.0-windows.zip', 'Windows setup ZIP', 'The complete connector, setup script, documentation, tests and Python wheel.'],
  ['archicad_codex_connector-0.1.0-py3-none-any.whl', 'Python wheel', 'Installable Python package for an existing Python environment.'],
  ['archicad_codex_connector-0.1.0.tar.gz', 'Source archive', 'Connector source and development files for version 0.1.0.'],
  ['SHA256SUMS', 'SHA-256 checksums', 'Verify the three release files after downloading.'],
];

function page(title, content) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive,nosnippet"><title>${title} — Kaan Downloads</title><link rel="stylesheet" href="/styles.css"></head><body><header><a class="brand" href="/"><span>K</span>Kaan Downloads</a><span class="eyebrow portal-label">Private access</span></header><main class="page">${content}</main><footer><p>Kaan Downloads · Archicad Connector 0.1.0</p><a href="https://kaan.win">kaan.win ↗</a></footer></body></html>`;
}

function login(message = '') {
  return page('Sign in', `<div class="login-layout"><div><p class="eyebrow">Your files, in one place</p><h1>Welcome back.</h1><p class="intro">Sign in to choose your connector downloads.</p><p class="fine">Use your download-site username and password.</p></div><form class="login-form" method="post" action="/login">${message ? `<p class="login-error" role="alert">${message}</p>` : ''}<label for="username">Username</label><input id="username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required maxlength="30"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required minlength="8" maxlength="1024"><button class="button" type="submit">Sign in →</button><p class="fine">Access is limited to the download-site owner.</p></form></div>`);
}

function home() {
  return page('Downloads', `<div class="portal-heading"><div><p class="eyebrow">Archicad Connector / v0.1.0</p><h1>Your downloads.</h1><p class="intro">Choose the complete Windows bundle or an individual release file.</p></div><form method="post" action="/logout"><button class="button secondary" type="submit">Sign out</button></form></div><section class="download-grid" aria-label="Release files">${FILES.map(([name, label, description], index) => `<article class="download-card"><p class="eyebrow">0${index + 1} / Release file</p><h2>${label}</h2><p>${description}</p><a class="button${index ? ' secondary' : ''}" href="/downloads/${name}">Download ${label} ↓</a></article>`).join('')}</section><section class="portal-links" aria-label="Documentation"><h2>Before you install</h2><div class="actions"><a class="button secondary" href="https://archicad.kaan.win">Project overview ↗</a><a class="button secondary" href="https://archicad.kaan.win/setup">Windows setup ↗</a><a class="button secondary" href="https://archicad.kaan.win/validation">Validation record ↗</a><a class="button secondary" href="https://github.com/kguluzada/archicad-codex-connector">GitHub source ↗</a></div></section><aside class="notice"><p>Python, licensed Archicad and the matching Tapir add-on are required separately. Native Windows/Archicad validation is pending; this release is a prerelease.</p></aside><p class="fine">This site requires login. Source and release files remain public on GitHub.</p>`);
}

function tokenFrom(req) {
  const value = (req.headers.cookie || '').split(';').map(s => s.trim()).find(s => s.startsWith(`${COOKIE}=`))?.slice(COOKIE.length + 1);
  return typeof value === 'string' && /^[A-Za-z0-9._~%+\/=\-]{20,2048}$/.test(value) ? value : null;
}

function settings() {
  const auth = JSON.parse(process.env.DOWNLOAD_AUTH || '{}');
  if (!/^[a-z0-9_]{3,30}$/.test(auth.username) || !/^[a-f0-9]{32}$/.test(auth.salt) || !/^[a-f0-9]{128}$/.test(auth.hash) || !/^[a-f0-9]{64}$/.test(auth.secret)) throw new Error('Authentication not configured');
  return auth;
}

function signature(payload, auth) {
  return createHmac('sha256', Buffer.from(auth.secret, 'hex')).update(payload + '\0' + auth.hash).digest('base64url');
}

function authorized(token, auth) {
  if (!token) return false;
  try {
    const parts = token.split('.');
    if (parts.length !== 2) return false;
    const [payload, supplied] = parts;
    const expected = signature(payload, auth);
    if (supplied.length !== expected.length || !timingSafeEqual(Buffer.from(supplied), Buffer.from(expected))) return false;
    const value = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
    return Number.isSafeInteger(value.exp) && value.exp > Date.now() && value.exp <= Date.now() + SESSION_SECONDS * 1000;
  } catch { return false; }
}

function cookie(res, token) {
  res.setHeader('Set-Cookie', `${COOKIE}=${token || ''}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${token ? SESSION_SECONDS : 0}`);
}

function html(req, res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(req.method === 'HEAD' ? undefined : body);
}

function redirect(res, location) {
  res.statusCode = 303;
  res.setHeader('Location', location);
  res.end();
}

async function credentials(req) {
  if (Number(req.headers['content-length'] || 0) > 4096) return null;
  let body = req.body;
  if (body === undefined) {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
      size += Buffer.byteLength(chunk);
      if (size > 4096) return null;
      chunks.push(Buffer.from(chunk));
    }
    body = Buffer.concat(chunks).toString('utf8');
  }
  if (Buffer.isBuffer(body)) body = body.toString('utf8');
  if (typeof body === 'string') body = Object.fromEntries(new URLSearchParams(body));
  if (!body || typeof body !== 'object' || Buffer.byteLength(JSON.stringify(body)) > 4096) return null;
  const { username, password } = body;
  if (typeof username !== 'string' || !/^[a-z0-9_]{3,30}$/i.test(username) || typeof password !== 'string' || password.length < 8 || password.length > 1024) return null;
  return { username: username.toLowerCase(), password };
}

export default async function handler(req, res) {
  res.setHeader('X-Robots-Tag', 'noindex, nofollow, noarchive, nosnippet');
  res.setHeader('Cache-Control', 'private, no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");
  const url = new URL(req.url, ORIGIN);
  const action = url.searchParams.get('action');
  if (req.headers.host !== 'download.kaan.win') {
    redirect(res, ORIGIN + (action === 'download' && FILES.some(([name]) => name === url.searchParams.get('file')) ? '/downloads/' + url.searchParams.get('file') : '/login'));
    return;
  }
  if (!['GET', 'HEAD', 'POST'].includes(req.method)) {
    res.setHeader('Allow', 'GET, HEAD, POST');
    html(req, res, 405, login('This request method is not supported.'));
    return;
  }
  if (req.method === 'POST' && (req.headers.origin !== ORIGIN || req.headers['sec-fetch-site'] === 'cross-site')) {
    html(req, res, 403, login('Request denied. Open this site directly and try again.'));
    return;
  }
  try {
    const token = tokenFrom(req);
    if (action === 'login') {
      if (req.method !== 'POST') { html(req, res, 200, login()); return; }
      const body = await credentials(req);
      if (!body) { html(req, res, 400, login('Enter your username and password.')); return; }
      const auth = settings();
      const digest = scryptSync(body.password, Buffer.from(auth.salt, 'hex'), 64);
      if (!timingSafeEqual(digest, Buffer.from(auth.hash, 'hex')) || body.username !== auth.username) { html(req, res, 401, login('Unable to sign in with these credentials.')); return; }
      const payload = Buffer.from(JSON.stringify({ exp: Date.now() + SESSION_SECONDS * 1000, nonce: randomBytes(16).toString('base64url') })).toString('base64url');
      const session = payload + '.' + signature(payload, auth);
      cookie(res, session); redirect(res, '/'); return;
    }
    if (action === 'logout') {
      if (req.method !== 'POST') { res.setHeader('Allow', 'POST'); html(req, res, 405, login('Use the sign-out button to end your session.')); return; }
      cookie(res, null);
      // shortcut: copied stateless sessions last at most one hour; add a session store for individual revocation.
      redirect(res, '/login'); return;
    }
    if (!['home', 'download'].includes(action)) { html(req, res, 404, page('Not found', '<h1>Page not found.</h1><a href="/">Back to downloads →</a>')); return; }
    if (req.method === 'POST') { res.setHeader('Allow', 'GET, HEAD'); html(req, res, 405, login('This request method is not supported.')); return; }
    if (!authorized(token, settings())) { cookie(res, null); redirect(res, '/login'); return; }
    if (action === 'home') { html(req, res, 200, home()); return; }
    const name = url.searchParams.get('file');
    if (!FILES.some(([file]) => file === name)) { html(req, res, 404, page('Not found', '<h1>File not found.</h1><a href="/">Back to downloads →</a>')); return; }
    const data = await readFile(join(process.cwd(), 'private', name));
    res.statusCode = 200;
    res.setHeader('Content-Type', name.endsWith('.zip') ? 'application/zip' : name === 'SHA256SUMS' ? 'text/plain; charset=utf-8' : 'application/octet-stream');
    res.setHeader('Content-Disposition', `attachment; filename="${name}"`);
    res.setHeader('Content-Length', data.length);
    res.end(req.method === 'HEAD' ? undefined : data);
  } catch {
    html(req, res, 503, login('The download service is unavailable. Please try again shortly.'));
  }
}
