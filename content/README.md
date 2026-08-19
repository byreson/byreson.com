# RESON content

This directory is the human-editable source of truth for Writing, Work, Now, About, Colophon, Lab, and future interest records. The builder is dependency-free and produces plain static files in `dist/`.

## Publish a piece of writing

1. Copy `writing/_template.md` to `writing/your-slug.md`.
2. Fill in every required front-matter value.
3. Write the piece in Markdown.
4. Keep `draft: true` while working.
5. Remove every `TODO(RESON)` marker and change to `draft: false` when it is ready.
6. Run `python build.py`, preview the result, and run `python scripts/check.py`.

Required fields are `title`, `description`, `date`, at least one `topic`, and `draft`. `slug` defaults to the filename but should usually be explicit. Dates use `YYYY-MM-DD`. If `image` is set, `image_alt` is required.

Published writing automatically receives:

- a canonical route at `/writing/{slug}/`;
- a row on `/writing/` and, for the three newest pieces, the homepage;
- the featured position on `/writing/` when `featured: true`;
- article metadata and JSON-LD;
- topic connections and related-writing suggestions;
- entries in `rss.xml`, `sitemap.xml`, `search-index.json`, and active Explore rooms.

Raw HTML in Markdown is escaped. Supported syntax includes headings, paragraphs, emphasis, links, images, lists, blockquotes, horizontal rules, inline code, and fenced code blocks. This constrained format keeps the renderer small and the content portable.

When `image` is set, writing rows on the homepage, `/writing/`, related-writing, and topic pages show a small thumbnail beside the entry automatically. Entries without an image stay text-only — never force a photograph onto a piece that doesn't have one. That front-matter `image` is the lead image and social card; it is separate from the media you place inside the body, below.

## Media inside an article

Put photographs and video anywhere between paragraphs. There is no limit on how many.

**A photo**

```markdown
![Rocky coastline and blue ocean at Kiama](/assets/photos/kiama-coast.jpg)
```

If the filename contains a space, wrap the path in angle brackets: `![Coast](</assets/photos/coastal photo.jpg>)`.

**A photo with a caption**

```markdown
{{ image
src="/assets/photos/kiama-coast.jpg"
alt="Rocky coastline and blue ocean at Kiama"
caption="Kiama, NSW."
}}
```

**A wide photo** — breaks out of the prose column to the site's media width:

```markdown
{{ image
src="/assets/photos/eclipse.jpg"
alt="A partial eclipse behind thin cloud"
caption="Partial eclipse."
size="wide"
}}
```

**A local video** — from `assets/video/`:

```markdown
{{ video
src="/assets/video/eclipse.mp4"
poster="/assets/photos/eclipse-poster.jpg"
caption="A short clip."
}}
```

**An external video** — YouTube or Vimeo only:

```markdown
{{ video
url="https://www.youtube.com/watch?v=VIDEO_ID"
title="What the video shows"
caption="Optional caption."
}}
```

Everything above also works on one line, e.g. `{{ image src="…" alt="…" }}`.

### Rules the build enforces

- `alt` is required on every image. Use `alt=""` only for a genuinely decorative one.
- `size` accepts `normal` (default) and `wide`. Nothing else.
- External video accepts YouTube and Vimeo only; any other host fails the build. YouTube uses the privacy-enhanced `youtube-nocookie.com` domain.
- An embedded video needs a `title` (or a `caption`) so it is announced properly by screen readers.
- A misspelled option fails the build rather than being ignored, so typos surface immediately.
- Raw HTML in Markdown stays escaped. `<iframe>`, `<script>` and inline event handlers can never be injected through an article.

Images get `loading="lazy"`, real `width`/`height` (read from the file, so nothing shifts as the page loads), and responsive `sizes`. Local video uses native controls with `preload="metadata"` — it never autoplays, loops, or starts muted. Embeds are lazy-loaded. Supply `captions="/assets/video/clip.vtt"` on a local video and it is attached as a caption track.

## Topics and Explore

`topics.json` defines the editorial order, names, descriptions, and optional record files for Explore. A topic is always visible on `/explore/`, but its detail route is generated only when published writing, published work, or a real record activates it. Empty rooms are labelled `Waiting for a story.` instead of being filled with invented material.

One article or project can use several topics while keeping one canonical source. The JSON arrays under `records/` are intentionally empty. Adding a real record activates that room. A record must have a `title`; other fields are flexible, and a `writing` value may connect it to a published writing slug.

## Now

Edit `now.json` to update both surfaces. Home shows the first three non-empty items; `/now/` shows the full snapshot. Blank labels or values are hidden. Update the date whenever the snapshot changes. The build does not expose an archive until more than one snapshot is genuinely worth keeping.

## Projects

Copy `projects/_template.md` to publish a factual case study. Keep `draft: true` until every statement can be shared accurately and remove `TODO(RESON)` before publishing. A published project appears on `/work/`, activates its relevant Explore topics, receives `/work/{slug}/`, and may appear in the two-item homepage selection when `featured: true`. New published projects need no other configuration — the Work index and homepage selection are generated automatically.

Project dates and years are optional because the builder must not invent chronology. `context`, `status`, `technologies`, `source`, and `live_url` are also optional; only add values that are public and verifiable:

- `status` is free text (e.g. "Completed", "In development", "Experiment") shown next to context/year — omit rather than force one.
- `source` renders a "View source" link on the Work index and the project page, only when the repository is genuinely public.
- `live_url` renders a "View live" link in the same places when a real deployment exists.
- `image` is a screenshot of the actual project — real UI, real output, a real diagram. Never stock or decorative imagery. It appears on the project page, beside the project on the Work index, and on the homepage for the two selected projects.

`/work/` also renders a Technologies list aggregated from the `technologies` arrays of every published project. It is derived, never hand-maintained: adding a project with a new technology adds it there automatically, and there is no separate skills list to keep in sync or inflate.

## Homepage photograph

`home.json` controls the single large photograph between the hero and Featured Writing. Leave `image` blank to omit the section entirely — no placeholder or empty space is shown. When set, `image_alt` is required; `caption` is free text (e.g. "Kiama, 2026"). Use one real, personal photograph — not stock or AI-generated imagery.

## Explore photographs

`explore-photos.json` is an array of up to three real photographs shown near the top of `/explore/`. Each entry needs `image` and `image_alt`; `caption` is optional. An empty array (the default) omits the strip entirely. This is not a gallery or carousel — keep it to a small, deliberate set.

## Experience and education

`experience.json` drives the Selected experience and Education blocks at the bottom of `/work/`,
below the projects. `roles[]` needs `organisation`; `title`, `location`, `note` and `project` are
optional, and `project` links a role to a published project slug. `education[]` needs
`qualification`; `institution` and `note` are optional.

No employment or graduation dates are recorded anywhere, so none are published — do not add one
from memory. `technology: false` marks a role as non-technology; the layout presents it honestly as
what it was rather than implying it was a software job.

## Site configuration

`site.json` holds a few values that don't belong to any one piece of content:

- `github`, `linkedin`, `email` — professional links shown on `/work/`. Leave blank to omit; never invent a URL or address.
- `cv` — the repository-relative path to a CV PDF (defaults to `assets/documents/Rijan-Pradhan-CV.pdf`). The "Download CV" action only appears once a real file exists at that path.
- `tagline` — an optional one-line professional description shown under the `/work/` heading. Leave blank rather than invent a title or specialisation that isn't verified elsewhere in the repository.
- `cusdis_app_id` — see Comments below.

## Comments

Individual Writing pages (`/writing/{slug}/`) can show a comment thread powered by [Cusdis](https://cusdis.com), a free, lightweight, account-free comment widget. It never appears on any other route.

1. Create a free site at cusdis.com and add byreson.com as a project.
2. Copy the App ID Cusdis gives you.
3. Paste it into `site.json`'s `cusdis_app_id` field.

Leave `cusdis_app_id` blank to keep comments off — no script loads and no widget renders; articles read normally either way. The Cusdis script is loaded with `async defer` only on article pages, and each thread is identified by the writing slug, so a slug rename starts a new thread.

## Pages

The concise copy for About, Colophon, and Lab lives under `pages/`. These files are generated into `/about/`, `/colophon/`, and `/lab/`. Colophon must describe the actual implementation; Lab should stay an honest empty state until a real experiment exists.

Any page may carry a portrait through front matter:

```yaml
image: assets/photos/rijan.png
image_alt: Portrait of Rijan Pradhan in a black hat, against a mossy rock face
image_caption: ""
```

When `image` is set, `image_alt` is required and the page renders as a two-column layout with the portrait beside the copy, collapsing to a single column on narrow screens. Leave `image` out and the copy simply keeps its natural measure — no gap, no placeholder.

## Drafts and verification fixtures

Two separate gates keep unfinished material off the public site, and the builder enforces both:

- `draft: true` — a real piece that is not ready yet.
- `demo: true` — a verification fixture that must never be published at all.

Find every fixture from the repository root with:

```text
rg -n "demo: true|\"demo\": true" content --glob "!README.md"
```

JSON fixtures carry a source-only `_source_note`, which is never rendered. The remaining fixtures
live in `records/*.json`; they keep the demo gate exercised against real content.

The three articles under `writing/` are **drafts, not fixtures**. They were written from verified
events and are waiting on your edit: adjust the wording to sound like you, set a real `date`, then
change `draft: true` to `draft: false` to publish. Nothing in them appears anywhere on the site
until you do.

## Preparing images

All images live under `assets/` and are copied to `dist/` unchanged — there is no build-time image processing, and no npm image pipeline. The builder reads each local file's real pixel dimensions and writes them into the `<img>` tag, so layout never shifts while a photograph loads. Prepare files by hand before adding them:

- **Homepage photograph:** JPEG, roughly 2000–2400px wide (16:9), aim for under 400KB.
- **About portrait:** JPEG, roughly 1200×1600px (3:4), aim for under 300KB.
- **Explore / writing images:** JPEG, roughly 1200×900px, aim for under 200KB.
- **Project screenshots:** PNG for UI captures (crisp text), actual capture resolution, aim for under 500KB. Screenshots are contained rather than cropped, so the whole interface stays visible.
- **Inline article photos:** JPEG or WebP. Around 1600px wide for `normal`, 2400px for `size="wide"`. The builder reads dimensions from PNG, JPEG and WebP.
- **Video:** MP4 (H.264/AAC) in `assets/video/`, alongside an optional poster image in `assets/photos/`. Keep clips short; they are served as static files with no streaming or transcoding.
- Strip EXIF, especially GPS location data, from any personal photograph before adding it. Most OS "export" or "share" flows do this; `exiftool -all= photo.jpg` also works.
- Write real, specific alt text describing what is actually in the frame — never "photo", and never a copy of the caption.
- Avoid spaces in filenames where you can. The builder percent-encodes them safely, but `coastal-clifftop.jpg` is easier to work with than `coastal photo.png`.

`python build.py` prints a warning for any image over 500KB. It never fails the build — it is a reminder to export a compressed JPEG, because photographs at 2MB+ noticeably delay the first meaningful paint.

## Build and validation

From the repository root:

```text
python build.py
python -m unittest discover -s tests -v
python scripts/check.py
```

Preview `dist/` through a local HTTP server before publishing. The generated directory must not be hand-edited or committed. Deployment only needs to serve that folder as static files.
