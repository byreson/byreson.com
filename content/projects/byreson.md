---
title: byreson.com
slug: byreson
description: An evolving digital home designed to hold professional work and the rest of a life without flattening either one.
date: 2026-08-15
year: 2026
context: Personal project
status: In development
source: https://github.com/byreson/byreson.com
live_url: https://byreson.com
topics:
  - technology
  - life
technologies:
  - HTML
  - CSS
  - JavaScript
  - Python
  - Cloudflare
featured: true
image: ""
image_alt: ""
draft: false
---

## The idea

This website is a personal digital home with a professional front door. It is designed to hold
projects, writing, interests, experiments, and personal history without reducing everything to a
portfolio.

Part of the point is ownership. Most of what people write ends up on platforms they do not control
and cannot take with them. This is the version I control: my domain, my files, my format.

## The approach

The public site is semantic HTML, modern CSS, and a small amount of progressive JavaScript. A
Python builder using only the standard library turns Markdown and JSON into static routes,
metadata, topic connections, RSS, a sitemap, and a lightweight search index.

Content drives everything. Publishing a piece of writing or a project means adding one file — the
routes, topic relationships, feed entries, sitemap records and index appearances are generated from
it. There is no page to update by hand.

## Technical decisions

**No framework.** The site is content and typography. React or a similar framework would add a
build pipeline, a dependency tree and a client bundle to a site whose defining quality is that it
does not need one. The browser gets HTML, CSS, fonts and about 6 KB of JavaScript for the mobile
menu. That is a deliberate engineering decision, not a limitation I am working around.

**Standard library only.** The builder has no third-party dependencies, so it does not rot. There
is no lockfile to audit and nothing to reinstall before it will run.

**Progressive enhancement.** Every route is a real file. Reading works with JavaScript disabled;
the script only enhances the responsive menu.

**Content integrity in the build.** Draft and verification content is gated by the compiler rather
than by remembering. Anything marked as a draft or a demo fixture cannot reach the published site,
and the build fails if an unfinished marker appears in published content.

## What I learned

Constraints are easier to work with than options. Deciding early that there would be no framework,
no database and no third-party runtime scripts removed most of the decisions I would otherwise have
spent time on, and the parts I did build got more attention as a result.
