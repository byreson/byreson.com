# byreson.com architecture

## Product model

RESON is a personal digital home with a professional front door. Its long-term shape is a set of connected personal modules, while its public interface follows a stricter rule: huge depth behind a small number of doors.

The primary information architecture is:

- **Home** — identity, featured and recent writing, selected work, and an invitation to explore
- **Work** — professional credibility and factual case studies
- **Writing** — the core personal publishing surface
- **Explore** — an editorial map across interests
- **About** — the person behind Reson

Now is a contextual route and homepage section rather than a permanent primary-navigation item. Interests remain topics under Explore instead of multiplying navigation links.

## Why the site has a small build

The original site was correctly a no-build static homepage. The publishing system introduces one concrete requirement that copied files cannot satisfy cleanly: one Markdown source must create a canonical route, metadata, topic relationships, related content, RSS, sitemap entries, and search records without duplicate configuration.

The smallest solution is a single Python standard-library builder. It adds no package manager or runtime dependency to the delivered site. The browser still receives ordinary HTML, CSS, fonts, images, and about 6 KB of progressive JavaScript.

## System flow

```text
content/writing/*.md ─┐
content/projects/*.md ├── build.py ──> dist/
content/now.json ─────┤                 ├── index.html
content/topics.json ──┤                 ├── writing/.../index.html
content/records/*.json┘                 ├── explore/.../index.html
content/pages/*.md ────┤                 ├── about|colophon|lab/index.html
templates/base.html ────────────────────├── now/index.html
index.html + CSS/JS/assets ─────────────├── work/.../index.html
                                       ├── rss.xml (+ feed.xml compatibility copy)
                                       ├── sitemap.xml
                                       └── search-index.json
```

Core content is present in the initial HTML. JavaScript enhances only the responsive menu; navigation and reading never depend on it.

## Repository map

```text
index.html                  hand-authored homepage shell with generated regions
style.css                   shared light editorial design system
content.css                 Phase Two typography and editorial route layer
script.js                   optional responsive-menu enhancement
build.py                    standard-library content compiler
templates/base.html         shared interior-page shell
templates/footer.html       shared global footer for every generated HTML page
content/
  pages/*.md               About, Colophon, and Lab source copy
  writing/_template.md      writing schema and authoring starter
  projects/_template.md     project case-study starter
  now.json                  one current snapshot
  home.json                 optional single homepage photograph
  explore-photos.json       optional Explore photo strip (up to three)
  site.json                 professional links, CV path, Cusdis app id
  topics.json               Explore taxonomy and editorial order
  records/*.json            future structured personal records
assets/fonts/               self-hosted Inter and Newsreader WOFF2 assets
assets/documents/            optional CV PDF (not committed until real)
scripts/check.py            structural and source-quality checks
tests/test_build.py         content/compiler unit tests
dist/                       generated, ignored production output
```

## Content model

Writing and projects use portable front matter plus constrained Markdown. `draft: true` is the safe default. `demo: true` marks verification fixtures and is treated as unpublished everywhere — writing, records, Now, and topic descriptions alike. Published content containing `TODO(RESON)` fails the build. Raw HTML is escaped, external protocols are allow-listed, images require alt text in front matter, and duplicate slugs fail.

A writing entry has one canonical source and any number of topics. Topic pages reference that entry; they never copy it. Related writing is ranked first by shared-topic count and then recency. Unknown but valid topic slugs can activate automatically, while `content/topics.json` controls the intentional Explore directory.

Explore lists every editorial topic but generates a topic route only when published writing, a published project, or a real record exists. That permits early honest empty states and later deep archives without changing the top-level UI.

Now is stored once in JSON and rendered at `/now/`. The date is retained so later archive work can preserve history without migrating the model.

Books, cinema, chess, running, and travel start as empty JSON arrays. Their records may connect to a writing slug, making narrative primary and structured facts secondary. No public module page exists until real records arrive.

Article bodies support inline media through two directives, `{{ image ... }}` and `{{ video ... }}`, alongside ordinary Markdown images. They are line-oriented `key="value"` blocks, which keeps them readable in raw Markdown, trivial to parse without a dependency, and simple for a future content manager to generate mechanically.

The directives are the only path from Markdown to a richer element. Raw HTML stays escaped, so an article can never inject a script, an event handler, or an arbitrary iframe. External video is restricted to an allow-list of providers: the URL is matched against a strict pattern, the video id is extracted, and the embed URL is rebuilt from a template rather than passed through. YouTube uses the privacy-enhanced domain, and `_headers` grants `frame-src` to those providers under `/writing/*` only.

Photography (`home.json`, `explore-photos.json`, writing and project `image` fields) follows the same rule as every other content type: a blank or missing field omits the block entirely, never a placeholder. `site.json` applies it to the professional layer — the "Download CV" action only appears once a real PDF exists at the configured path, and GitHub/LinkedIn/email links only render for values actually present. Comments (Cusdis) are opt-in through `site.json`'s `cusdis_app_id` and load only on individual Writing pages; `_headers` grants Cusdis a scoped Content-Security-Policy exception under `/writing/*` only.

## Why the architecture stayed

A framework migration (Astro, Next, Vite) was considered and rejected. The concrete problems a framework solves — component reuse, content collections, image optimisation, interactive islands — are either already solved here or not yet real:

- Authoring is already Markdown/JSON; a content layer would add configuration, not capability.
- Reuse is handled by builder functions and two stylesheets; there is no duplicated markup to deduplicate.
- The delivered site ships ~6 KB of JavaScript for one menu. A framework would add a bundle to a site whose defining quality is that it does not need one.
- Future interactive modules (maps, running charts, chess boards) can be added as isolated progressive-enhancement scripts on their own routes without the rest of the site paying for them.

The cost of migrating — rebuilding every route, re-verifying URLs, RSS, sitemap, JSON-LD, draft/demo gating, and the accessibility work — buys nothing measurable today. That calculus changes only when a genuinely stateful, interactive surface appears; until then the standard-library compiler stays.

## Two content widths

Type and media are held to different measures. `--shell-width` (82rem) governs navigation, headings, prose, and list rows so line length stays readable on any monitor. `--media-width` (112rem) is used only by `.media-shell`: the homepage photograph, article lead images, and project screenshots.

That single distinction does the work of a redesign. Photography reads as a deliberate editorial moment rather than an oversized attachment, large monitors stop showing a narrow column adrift in empty space, and article prose never widens past a comfortable measure to accommodate an image.

## Typography and design system

Inter Variable carries navigation, UI, headings, homepage copy, metadata, and project pages. Newsreader Variable is limited to article decks and prose. A system monospace stack handles code. Fluid role-based sizes use `clamp()`, article measure is constrained independently from the site shell, and important text avoids ultra-light weights.

The local WOFF2 set consists of one Inter roman file and Newsreader roman/italic files. Inter is the only universal preload. Article routes additionally preload Newsreader roman; italic remains on demand. Long-lived immutable font caching is declared in `_headers`.

One permanent light palette uses warm paper, dark ink, a warm muted grey, and a restrained slate-indigo accent. `color-scheme: only light` keeps native browser controls consistent even when the operating system uses dark mode. Typography, whitespace, alignment, and rules do most of the visual work; cards, radii, shadows, and decorative effects are intentionally rare.

Every colour is declared as a token on `:root` and referenced nowhere else as a literal, so a coherent site-wide second theme remains possible later without touching layout. Dark mode is deliberately not implemented: the warm paper ground is the identity, the photography is composed against it, and a second theme would double the design and QA surface for no current product gain.

The type scale descends from a single peak. `--type-display` is used by exactly one element — the RESON wordmark — and every other level (`--type-lead`, `--type-heading`, `--type-subheading`, `--type-row`) steps down from it. Before this, section headings, page titles, and the featured story were all near-display size, so nothing on a page read as primary.

## Performance, accessibility, and privacy

- static HTML and no client router
- no third-party runtime requests
- no framework or CSS library
- WOFF2 variable fonts with swap and deliberate preloads
- semantic landmarks and one page heading
- skip link, focus states, keyboard menu handling, and Escape support
- touch-sized controls and responsive layouts from 320 px upward
- reduced-motion and forced-colours considerations
- no analytics, trackers, accounts, forms, or cookies
- security and privacy headers suitable for static hosting

## Scale and future modules

The year-grouped Writing index scales independently of the homepage, which always shows only the newest few entries. Explore remains the stable discovery surface as modules grow. Future Movies, Books, Chess, Running, Travel, Photos, Music, Space, and Lab views can consume records and topics without joining primary navigation.

`search-index.json` already normalises writing, work, and topic discovery into a small local format. Do not add a search UI or dependency until the archive is difficult to browse. When record counts justify it, extend the same index with record adapters rather than create parallel search systems.

Possible future additions should follow these thresholds:

1. Add a topic or record module when real content exists, not to complete a matrix.
2. Add Now archives when more than one snapshot is worth keeping.
3. Add a local search interface when topic and chronological browsing becomes insufficient.
4. Add image processing only when personal photography creates a repeatable optimisation problem.
5. Add a framework or database only when interactive state or server-owned data cannot be handled cleanly by this static compiler.

## Deliberate exclusions

React, TypeScript, Vite, npm, a client router, Docker, a database, a CMS, GraphQL, analytics, and hosted search are not present. They do not solve the current product problem. The content compiler is intentionally small, auditable, and replaceable because the Markdown and JSON sources remain portable.

Cloudflare Pages must publish the generated `dist/` directory after running `python build.py`. The route folders in `dist/` are the routing system; there is no browser-history router and no SPA fallback. A top-level generated `404.html` intentionally preserves real not-found responses.

The Pages dashboard remains the source of truth because this repository has no existing Wrangler configuration or Pages Functions bindings. Do not invent a Worker configuration or project name; use the settings documented in `CLOUDFLARE.md` for the existing Pages project.
