# Cloudflare Pages routing

byreson.com is a generated multi-page static site, not a React single-page application. `build.py` creates one real `index.html` for every route under `dist/`.

## Existing Pages project settings

Configure the existing Cloudflare Pages project in **Settings → Build → Build configurations**:

| Setting | Value |
| --- | --- |
| Framework preset | None |
| Production branch | `main` |
| Root directory | repository root / blank |
| Build command | `python build.py` |
| Build output directory | `dist` |

The output directory is essential. Publishing the repository root exposes only the source homepage because the generated route directories are intentionally ignored by Git.

Do not add an SPA fallback such as `/* /index.html 200`. The built site contains a top-level `404.html`, so Cloudflare Pages will serve real nested files such as `dist/writing/index.html` at `/writing/` and preserve an actual 404 for unknown URLs.

The build copies `_headers` and `_redirects` into `dist/`. Those files provide security/caching rules and block direct access to source-only repository paths; they are not client-router fallbacks.

## Local production check

```text
python build.py
python -m http.server 4173 --directory dist
python -m unittest discover -s tests -v
python scripts/check.py
```

Test both `/writing` and `/writing/`. The local server redirects the extensionless URL to the directory route, matching the clean-URL shape Cloudflare Pages serves.

## After the next authorized deployment

Verify `/`, `/work`, `/writing`, `/explore`, `/about`, `/now`, representative topic and article routes, and a deliberately unknown URL. The unknown URL must return the custom 404 rather than the homepage.

Cloudflare references:

- [Build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/)
- [Serving Pages and route matching](https://developers.cloudflare.com/pages/configuration/serving-pages/)
- [Redirects](https://developers.cloudflare.com/pages/configuration/redirects/)
