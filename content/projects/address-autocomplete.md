---
# Outcome/results section intentionally absent: no verified metrics are on record.
# Rijan — if you can share real outcomes from this work, add a "## The outcome" section.
title: Address Autocomplete
slug: address-autocomplete
description: Address autocomplete and property information tooling built during a software development internship at Titan Capital.
context: Software development internship, Titan Capital
status: Completed
topics:
  - technology
technologies:
  - JavaScript
  - Node.js
  - Express.js
  - Google Maps JavaScript API
  - Geoscape Predictive API
  - MySQL
  - Git
featured: true
image: ""
image_alt: ""
draft: false
---

## The problem

Property workflows depend on addresses being entered correctly. Free-text address fields produce
variations, typos, and records that are difficult to match against real properties later. The work
was to let someone start typing an address and choose a real, verified one instead.

## My role

I worked on this as a software development intern at Titan Capital in Sydney: building the address
autocomplete behaviour and the service layer connecting the application to external address and
location providers.

## What I built

Address autocomplete integrated into the property information workflow, backed by a Node.js and
Express service that sat between the front end and the external address APIs — the Google Maps
JavaScript API and the Geoscape Predictive API — with MySQL behind the application for property and
address data.

Routing the provider calls through a backend proxy rather than calling them from the browser keeps
API credentials off the client, gives one place to shape provider responses into the format the
application expects, and means a provider can change without the front end changing with it.

## What I learned

Most of the interesting work in an integration like this is not the autocomplete widget. It is the
boundary: what the external service returns, what your application actually needs, and the
translation layer in between that has to survive both sides changing.
