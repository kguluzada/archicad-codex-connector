import assert from 'node:assert/strict';
import { after, before, beforeEach, test } from 'node:test';
import { createServer, request as httpRequest } from 'node:http';
import { readFile, access } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHmac, scryptSync } from 'node:crypto';
import handler from '../api/portal.mjs';

const auth = { salt: 'ab'.repeat(16), secret: 'cd'.repeat(32) };
auth.hash = scryptSync('test-password', Buffer.from(auth.salt, 'hex'), 64).toString('hex');
let server, base;
const initialDirectory = process.cwd();
const initialAuth = process.env.DOWNLOAD_AUTH;
before(async () => {
  process.chdir(resolve(import.meta.dirname, '..'));
  server = createServer((req, res) => handler(req, res));
  await new Promise(done => server.listen(0, '127.0.0.1', done));
  base = `http://127.0.0.1:${server.address().port}`;
});
beforeEach(() => { process.env.DOWNLOAD_AUTH = JSON.stringify(auth); });
after(async () => {
  if (initialAuth === undefined) delete process.env.DOWNLOAD_AUTH; else process.env.DOWNLOAD_AUTH = initialAuth;
  process.chdir(initialDirectory);
  await new Promise(done => server.close(done));
});
function request(path, options = {}) {
  return new Promise((done, fail) => {
    const req = httpRequest(base + path, { method: options.method || 'GET', headers: { Host: 'download.kaan.win', ...options.headers } }, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => {
        const headers = new Headers();
        for (const [key, value] of Object.entries(response.headers)) {
          for (const item of Array.isArray(value) ? value : [value]) if (item !== undefined) headers.append(key, item);
        }
        done(new Response(Buffer.concat(chunks), { status: response.statusCode, headers }));
      });
    });
    req.on('error', fail);
    req.end(options.body);
  });
}
function signIn(headers = {}, body = 'password=test-password') {
  return request('/api/portal?action=login', { method: 'POST', body, headers: { Origin: 'https://download.kaan.win', 'Content-Type': 'application/x-www-form-urlencoded', ...headers } });
}
async function signedCookie() {
  const response = await signIn();
  assert.equal(response.status, 303);
  return response.headers.get('set-cookie').split(';')[0];
}
function timedCookie(exp) {
  const payload = Buffer.from(JSON.stringify({ exp })).toString('base64url');
  const mac = createHmac('sha256', Buffer.from(auth.secret, 'hex')).update(payload + '\0' + auth.hash).digest('base64url');
  return `__Host-download-session=${payload}.${mac}`;
}

test('anonymous home/files redirect and login has robots metadata and password form', async () => {
  for (const action of ['home', 'download&file=archicad-connector-0.1.0-windows.zip']) {
    const response = await request('/api/portal?action=' + action);
    assert.equal(response.status, 303);
    assert.equal(response.headers.get('location'), '/login');
    assert.match(response.headers.get('x-robots-tag'), /noindex/);
    assert.equal(response.headers.get('cache-control'), 'private, no-store');
  }
  const response = await request('/api/portal?action=login');
  const html = await response.text();
  assert.match(html, /name="robots" content="noindex/);
  assert.match(html, /type="password"/);
  assert.doesNotMatch(html, /name="username"/);
  assert.match(html, /method="post" action="\/login"/);
  assert.doesNotMatch(html, /archicad-connector-0.1.0-windows.zip/);
});

test('valid login sets secure host-only cookie and dashboard has file/documentation buttons', async () => {
  const response = await signIn();
  assert.equal(response.status, 303);
  assert.equal(response.headers.get('location'), '/');
  const cookie = response.headers.get('set-cookie');
  for (const flag of ['HttpOnly', 'Secure', 'SameSite=Strict', 'Path=/', 'Max-Age=3600']) assert.ok(cookie.includes(flag));
  assert.ok(!cookie.includes('Domain='));
  const dashboard = await request('/api/portal?action=home', { headers: { Cookie: cookie.split(';')[0] } });
  assert.equal(dashboard.status, 200);
  const html = await dashboard.text();
  assert.equal((html.match(/href="\/downloads\//g) || []).length, 4);
  assert.match(html, /Windows setup ↗/);
  assert.match(html, /GitHub source ↗/);
  assert.doesNotMatch(html, /test-password/);
});

test('authenticated artifacts match exact bytes from a different working directory; unlisted/traversal names are refused', async () => {
  const Cookie = await signedCookie();
  const directory = process.cwd();
  process.chdir(initialDirectory);
  try {
    for (const name of ['archicad-connector-0.1.0-windows.zip', 'archicad_codex_connector-0.1.0-py3-none-any.whl', 'archicad_codex_connector-0.1.0.tar.gz', 'SHA256SUMS']) {
      const response = await request('/api/portal?action=download&file=' + name, { headers: { Cookie } });
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('content-disposition'), `attachment; filename="${name}"`);
      assert.deepEqual(Buffer.from(await response.arrayBuffer()), await readFile(new URL('../private/' + name, import.meta.url)));
    }
    for (const file of ['../api/portal.mjs', 'private/SHA256SUMS', 'unlisted.zip']) {
      assert.equal((await request('/api/portal?action=download&file=' + encodeURIComponent(file), { headers: { Cookie } })).status, 404);
    }
  } finally { process.chdir(directory); }
});

test('forged, altered, expired and overlong sessions cannot access downloads', async () => {
  const valid = await signedCookie();
  const candidates = [valid.slice(0, -1) + (valid.endsWith('a') ? 'b' : 'a'), '__Host-download-session=forged-session-value.signature', timedCookie(Date.now() - 1), timedCookie(Date.now() + 7200000), '__Host-download-session=' + 'a'.repeat(2100)];
  for (const Cookie of candidates) {
    const response = await request('/api/portal?action=home', { headers: { Cookie } });
    assert.equal(response.status, 303);
    assert.match(response.headers.get('set-cookie'), /Max-Age=0/);
  }
});

test('wrong passwords do not create a session; rotation invalidates existing sessions', async () => {
  for (const body of ['password=wrong-password', 'password=another-wrong-password']) {
    const response = await signIn({}, body);
    assert.equal(response.status, 401);
    assert.equal(response.headers.get('set-cookie'), null);
  }
  const Cookie = await signedCookie();
  process.env.DOWNLOAD_AUTH = JSON.stringify({ ...auth, hash: 'ef'.repeat(64) });
  assert.equal((await request('/api/portal?action=home', { headers: { Cookie } })).status, 303);
});

test('cross-site login/logout and oversize credentials are refused', async () => {
  assert.equal((await signIn({ Origin: 'https://evil.example' })).status, 403);
  assert.equal((await signIn({ 'Sec-Fetch-Site': 'cross-site' })).status, 403);
  assert.equal((await signIn({}, 'password=' + 'a'.repeat(5000))).status, 400);
  assert.equal((await signIn({}, 'password=short')).status, 400);
  assert.equal((await request('/api/portal?action=logout', { method: 'POST' })).status, 403);
});

test('logout clears the browser cookie and GET cannot log out', async () => {
  assert.equal((await request('/api/portal?action=logout')).status, 405);
  const response = await request('/api/portal?action=logout', { method: 'POST', headers: { Cookie: await signedCookie(), Origin: 'https://download.kaan.win' } });
  assert.equal(response.status, 303);
  assert.equal(response.headers.get('location'), '/login');
  assert.match(response.headers.get('set-cookie'), /Max-Age=0/);
  assert.equal((await request('/api/portal?action=home')).status, 303);
});

test('missing/malformed credentials fail closed and are not shown in responses', async () => {
  for (const setting of ['{}', 'not json', JSON.stringify({ ...auth, secret: 'short' })]) {
    process.env.DOWNLOAD_AUTH = setting;
    const response = await signIn();
    assert.equal(response.status, 503);
    assert.equal(response.headers.get('set-cookie'), null);
    assert.doesNotMatch(await response.text(), /test-password|scrypt|DOWNLOAD_AUTH/);
    assert.equal((await request('/api/portal?action=home')).status, 503);
  }
});

test('alternate host redirects are fixed; HEAD authenticates but has no file body', async () => {
  const alternate = await request('/api/portal?action=download&file=SHA256SUMS', { headers: { Host: 'archicad.kaan.win' } });
  assert.equal(alternate.status, 303);
  assert.equal(alternate.headers.get('location'), 'https://download.kaan.win/downloads/SHA256SUMS');
  const response = await request('/api/portal?action=download&file=SHA256SUMS', { method: 'HEAD', headers: { Cookie: await signedCookie() } });
  assert.equal(response.status, 200);
  assert.equal(await response.text(), '');
  assert.ok(Number(response.headers.get('content-length')) > 0);
});

test('deployment config places files outside output and declares noindex', async () => {
  // Vercel serves an existing index.html before applying host-specific rewrites.
  await assert.rejects(readFile('public/index.html'), {code: 'ENOENT'});
  const config = JSON.parse(await readFile('vercel.json', 'utf8'));
  assert.equal(config.outputDirectory, 'public');
  assert.equal(config.functions['api/portal.mjs'].includeFiles, 'private/**');
  const noindex = config.headers.find(route => route.has?.[0]?.value === 'download.kaan.win');
  assert.match(noindex.headers.find(header => header.key === 'X-Robots-Tag').value, /noindex/);
  await assert.rejects(access('public/downloads'));
  await assert.rejects(access('public/private'));
});
