# GitHub and download hosting

Source repository: https://github.com/kguluzada/archicad-codex-connector

- `archicad.kaan.win`: public project, setup and validation pages.
- `download.kaan.win`: a login screen and download buttons for the ZIP, wheel, source archive and checksums. Access through this site requires a separate shared password.
- `kaan.win`: existing portfolio, on its existing Vercel project.

The Vercel project uses `site/` as its root and serves `site/public/` as static output. Production deployments use the repository's `main` branch. The dependency-free Node.js function in `site/api/portal.mjs` renders the login/download pages and checks a server-side scrypt password hash. The production-only sensitive `DOWNLOAD_AUTH` environment variable contains the salt, hash and session signing key; plaintext passwords are not uploaded. Sessions use HMAC-SHA256 signatures, expire within one hour, and are carried only in an HttpOnly, Secure, SameSite=Strict host-only cookie. Password-hash or signing-key rotation invalidates sessions. Login/logout POSTs require the exact download-site origin, or strictly `Sec-Fetch-Site: same-origin` when an embedded browser sends a missing or `null` origin. Cross-site requests and other origins are rejected. There is no registration or account database.

Logout clears the browser cookie. A previously copied stateless token remains valid until expiry or credential/key rotation; add a session store if individual session revocation becomes necessary. Vercel's firewall limits POST requests on the download host to 10 per minute per IP, covering both the login URL and direct function URL. The local portfolio has authentication source code, but the deployed portfolio API returned 404, so its account service is not used or changed.

Release files live in `site/private/`, outside static output, and are bundled only into the server function. Both clean download routes and direct function routes check access. The host-specific `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet` header covers the download host, and server HTML includes matching robots metadata. Responses containing sessions/files are never cached. `robots.txt` permits crawling so compliant crawlers can see the noindex rule; it is not used as a privacy boundary. Search engines may need to recrawl previously indexed URLs.

The repository, historical GitHub source and GitHub release assets remain public. Portal login does not make those copies confidential. DNS is already authoritative on Vercel; the two subdomains use its managed records. Do not reassign the apex or replace the DNS zone.

## Publish a release

After updating the package version and the page/download URLs, build wheel/source artifacts with `python -m build`, then run `python scripts/package_release.py`. This script creates a checked ZIP of connector source, tests, documentation, examples, lockfile, setup scripts and wheel; it excludes the website, research clones and local environments. Dependencies, Python and native applications are not bundled. An internet connection is needed for setup dependencies.

Commit the source and `site/` release files, then push and deploy the Vercel project with output directory `public`. Publish the four files in `dist/` as GitHub release assets. Keep releases marked prerelease until the Windows live acceptance checklist passes. Run `node --test site/tests/portal.test.mjs` for authentication, cookie, origin, expiry/rotation, file-whitelist and failure checks. Verify anonymous requests redirect to login, authenticated downloads have the expected attachment header and SHA-256, noindex is present, and the existing apex page still loads after deploying.

GitHub's tag source archive contains the website too. The Windows ZIP intentionally contains only the connector deliverables.
