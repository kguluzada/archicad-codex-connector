# GitHub and download hosting

Source repository: https://github.com/kguluzada/archicad-codex-connector

- `archicad.kaan.win`: public project, setup and validation pages.
- `download.kaan.win`: the root URL redirects to the Windows setup ZIP with an attachment response header.
- `kaan.win`: existing portfolio, on its existing Vercel project.

The new Vercel project serves only `site/`, without a JavaScript framework or build dependencies. Its Git integration deploys `main`. Host-specific redirects and download headers live in `site/vercel.json`. DNS is already authoritative on Vercel; attaching the two subdomains uses its managed records. Do not reassign the apex or replace the DNS zone.

## Publish a release

After updating the package version and the page/download URLs, build wheel/source artifacts with `python -m build`, then run `python scripts/package_release.py`. This script creates a checked ZIP of connector source, tests, documentation, examples, lockfile, setup scripts and wheel; it excludes the website, research clones and local environments. Dependencies, Python and native applications are not bundled. An internet connection is needed for setup dependencies.

Commit the source and `site/` release files, then push. Publish the four files in `dist/` as GitHub release assets. Keep releases marked prerelease until the Windows live acceptance checklist passes. Verify anonymous HTTPS page responses, the download's attachment header and exact SHA-256, and the existing apex page after deploying.

GitHub's tag source archive contains the website too. The Windows ZIP intentionally contains only the connector deliverables.
