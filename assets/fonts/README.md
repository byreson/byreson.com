# Local typefaces

RESON self-hosts a deliberately small Latin-only variable-font set:

- `inter-latin-variable.woff2` — Inter variable, weights 100–900, used for the interface and the homepage.
- `newsreader-latin-variable.woff2` — Newsreader variable roman, weights 200–800, used only for long-form reading.
- `newsreader-latin-italic-variable.woff2` — Newsreader variable italic, weights 200–800, used only for long-form reading.

The files were downloaded from the Google Fonts static font service on 15 August 2026. The precise upstream URLs used are recorded below so the assets can be audited or refreshed without guessing:

- `https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2`
- `https://fonts.gstatic.com/s/newsreader/v26/cY9AfjOCX1hbuyalUrK4397yjA.woff2`
- `https://fonts.gstatic.com/s/newsreader/v26/cY9CfjOCX1hbuyalUrK439vCjohC.woff2`

Both families use the SIL Open Font License 1.1. Their upstream license texts are kept beside the font files as `OFL-Inter.txt` and `OFL-Newsreader.txt`.

Inter is preloaded on every page because it is visible immediately. Newsreader is preloaded only on article routes. All font files use `font-display: swap`, have metric-compatible fallbacks, and receive immutable caching headers in production.
