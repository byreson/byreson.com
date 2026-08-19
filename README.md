# RESON

[byreson.com](https://byreson.com/) is the digital home of Rijan Bahadur Pradhan, who uses Reson as his personal online identity. It has a professional front door, but it is built to hold much more than a résumé: work, writing, interests, experiments, memories, and a long personal archive.

The public interface stays deliberately small. The RESON wordmark is Home; Work, Writing, Explore, and About are the main doors. Now is a contextual snapshot, while Colophon and Lab sit quietly underneath the primary navigation.

## What this repository uses

- semantic HTML
- modern CSS
- a small amount of vanilla JavaScript
- a dependency-free Python standard-library builder
- portable Markdown and JSON content

There is no React, framework, npm, package installation, database, CMS, client router, analytics, or third-party runtime request. The build produces ordinary static files in `dist/`.

## Local development

Python 3.10 or newer is the only tool required for the publishing workflow.

```text
python build.py
python -m http.server 4173 --directory dist
```

Then open `http://127.0.0.1:4173/`. No installation command is required. Do not edit `dist/`; it is replaced on every build.

## Quality checks

```text
python -m py_compile build.py scripts/check.py tests/test_build.py tests/test_home.py tests/test_rendering.py
python -m unittest discover -s tests -v
python build.py
python scripts/check.py
git diff --check
```

The custom checker audits generated HTML structure, duplicate IDs, internal links and fragments, image alt attributes, JSON-LD, RSS, sitemap XML, the local search index, CSS brace balance, line endings, trailing whitespace, and draft leakage.

## Publishing writing

Writing lives in `content/writing/`. Copy `content/writing/_template.md`, write ordinary Markdown, and keep `draft: true` until the piece is ready. A published file automatically creates its route, metadata, topic relationships, related-writing links, RSS item, sitemap entry, search record, and homepage/index appearances.

For example:

```text
content/writing/why-eclipses-feel-different.md
```

One piece can use multiple topics without being duplicated:

```yaml
topics:
  - space
  - cinema
  - philosophy
```

Set `featured: true` to place a published piece in the featured area on `/writing/`. If several pieces are marked featured, the newest one is used. See `content/README.md` for the complete workflow and supported Markdown.

## Content map

- `content/writing/` — blog posts, stories, opinions, questions, and notes
- `content/projects/` — factual project case studies used by Home and Work
- `content/pages/` — About, Colophon, and Lab copy
- `content/now.json` — the current snapshot rendered at `/now/`
- `content/topics.json` — Explore order, labels, descriptions, and record connections
- `content/records/` — future books, cinema, chess, running, and travel records

No opinions, reviews, memories, results, or achievements are generated on Rijan's behalf. Empty areas remain intentional until real material exists.

## Design and fonts

The permanent palette is warm paper, dark ink, quiet grey, and a restrained slate-indigo Reson accent. Inter Variable carries the interface, homepage, headings, and project pages. Newsreader Variable is reserved for long-form article decks and prose. Both are self-hosted as licensed WOFF2 files under `assets/fonts/` and use `font-display: swap`. Inter is preloaded site-wide; Newsreader is preloaded only on article routes.

The site uses one light editorial identity alongside fluid type, keyboard navigation, visible focus, a mobile menu, and useful content without JavaScript.

## Generated output

`python build.py` creates:

- `/work/` and one route per published project
- `/writing/` and one route per published piece
- `/explore/` and only the topic rooms containing real writing, work, or records
- `/now/`, `/about/`, `/colophon/`, and `/lab/`
- `rss.xml`, a backwards-compatible `feed.xml` copy, `sitemap.xml`, and `search-index.json`
- the homepage, shared assets, headers, redirects, 404 page, and local fonts

The search index includes writing, work, and topic discovery, but is intentionally not exposed as a search UI yet. It gives a future local search feature one stable source without adding a dependency before the archive needs it.

## Hosting and privacy

The `dist/` directory is the only deployable artifact. The existing Cloudflare Pages project must run `python build.py` from the repository root and publish `dist`; publishing the repository root serves only the source homepage and makes generated routes return 404.

This is a multi-page static site, not an SPA. Do not add a catch-all rewrite to `index.html`: every published route has its own generated file, and the top-level `404.html` must remain a real not-found response. `_headers` and `_redirects` are copied into the build output.

See `CLOUDFLARE.md` for the exact existing-project settings and verification checklist.

This repository does not prove that a Cloudflare Pages project or Git integration is connected; DNS, project settings, deployment, and secrets remain outside the repository. The site has no tracking, advertising, cookies, accounts, forms, or third-party runtime scripts. Never commit credentials or publish private image metadata.

No deployment, repository-visibility change, GitHub push, or pull request should happen without explicit permission. See `ARCHITECTURE.md` for system decisions and `AGENTS.md` for repository rules.
