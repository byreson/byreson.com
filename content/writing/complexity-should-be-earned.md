---
title: I considered React for this site, then didn't use it
slug: complexity-should-be-earned
description: Notes on choosing a boring architecture on purpose, and what would actually change my mind.
date: 2026-08-19
topics:
  - technology
featured: false
image: ""
image_alt: ""
demo: false
draft: false
---

When I was working out how to build this site, I looked at the obvious options. React. Next. Astro.
All of them are good, and I have used enough of that world to know I could have made any of them
work.

I went with a Python script and static HTML instead. Not because frameworks are bad, and not as a
statement. I just could not answer a fairly basic question: what problem would it solve here?

## What the site actually needs to do

Turn Markdown and JSON into pages. Give every article a URL, some metadata, topic connections, an
RSS entry and a sitemap record. Look right on a phone. Load fast.

That is the whole requirement. A framework would do all of that competently, and it would also
bring a dependency tree, a build pipeline, a lockfile and a JavaScript bundle shipped to anyone who
opens the page.

For a site that is text and photographs, I would be paying that cost for capability I would not be
using.

## The thing I keep noticing

Complexity is easy to add and very hard to remove.

Every dependency is a decision you have to keep re-making. It needs updating. It has security
advisories. It has opinions that leak into how you structure things. Some of it will be abandoned
in three years. None of that is a disaster on its own, but it compounds, and it compounds fastest on
personal projects, because those are the ones nobody is paid to maintain.

The version of this site that still builds in five years is the boring one. The builder imports
nothing but Python's standard library. There is no install step. If I come back to it after a long
gap, it runs.

## What would actually change my mind

I want to be clear that this is not a permanent position. It is a decision that fits the current
requirements, and the requirements will move.

If I build something here that needs real interactive state, that is a genuine reason. A proper map
of places I have been, with filtering. Running data that you can actually query rather than read.
Something with a chess board in it that responds to you. At that point the static approach stops
being simple and starts being a workaround, and working around your own architecture is the signal
you picked the wrong one.

The rule I am trying to follow is that complexity should be earned by a problem, not adopted in
advance in case a problem shows up. Adopting it early feels like preparation. Mostly it is just
paying now for something you might never need.

For now, the site is HTML, CSS, about 6 KB of JavaScript for the menu, and a script that generates
files. It does exactly what I need. When that stops being true I will change it, and I will be able
to say precisely why.
