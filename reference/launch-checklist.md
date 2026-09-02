# Launch checklist

Ordered so that each step's output feeds the next. Everything marked **manual** cannot be
done over the REST API, do those in wp-admin and tick them off explicitly.

## 1. Access

- [ ] `.env` with `WP_URL`, `WP_USER`, `WP_APP_PASSWORD` (WP Admin → Users → Profile →
      Application Passwords)
- [ ] `python -c "from scripts.wp_api import WP; print(WP().check())"` shows
      `is_admin: True` and `greenshift: True`
- [ ] Design source reachable (Figma PAT, Paper file open, or screenshots in `input/`)
- [ ] Note what the host already provides, managed hosts usually cover caching, security
      and backups, so do not install plugins that duplicate them

## 2. Design system

- [ ] Palette run through `python scripts/check_contrast.py --bg <surface> --fg …`; fix the
      **token**, not the usage, before anything is built on it
- [ ] `python scripts/stylebook.py push reference/starter-tokens.json`
- [ ] Fonts loaded (theme Customizer / theme.json), matching `--gt-font-*`
- [ ] `python scripts/stylebook.py verify`, tokens and classes reach the front end

## 3. Content

- [ ] `python scripts/prep_images.py build`, **every raster image is WebP**; nothing
      upscaled; SVG left alone
- [ ] `python scripts/prep_images.py upload`, alt text present for every image, set on the
      attachment as well as the block
- [ ] `python scripts/prep_images.py audit` returns zero non-WebP images
- [ ] Site logo set, **with alt text on the attachment** (`alt_text` via
      `POST /wp/v2/media/<id>`), the header logo link has no other accessible name
- [ ] Pages generated and pushed as drafts with `"template": "no-title"`
- [ ] Header template part edited surgically; footer rewritten
- [ ] Menu items point at real slugs, built from **published** pages only (never link to a
      draft), and root-relative rather than absolute
- [ ] Post titles are human labels; the keyword-loaded version lives in the SEO plugin only

## 4. Quality gates

- [ ] Backend chosen deliberately (`greenshift` needs the plugin active; `core` does
      not) and the same one used for every page
- [ ] `python scripts/verify.py --all` passes on every page
- [ ] `python scripts/check_links.py`, no broken links, no dead anchors, nav consistent
- [ ] Prose classes cap at 65-75ch; no full-width section runs unconstrained body copy
- [ ] Page statuses re-read after the final push (a REST write can change them)
- [ ] Browser check at 375px: no horizontal scroll
      (`document.documentElement.scrollWidth <= innerWidth`), grids collapse, footer stacks
- [ ] Keyboard pass: visible focus on every link, button, input; menu operable
- [ ] Any interactive feature tested **on the front end** (never the editor canvas)
- [ ] Icon-only controls have `aria-label`; toggles expose `aria-expanded` / `aria-pressed`

## 5. Launch stack

- [ ] `python scripts/launch.py plugins`
- [ ] **manual** Rank Math setup wizard
- [ ] **manual** Settings → Permalinks → Save (flushes rules; sitemap 404s without it)
- [ ] **manual** FluentSMTP provider connected and authenticated
- [ ] `python scripts/launch.py form "<Business>"` → embed the shortcode
- [ ] `python scripts/launch.py emails <form_id> <to@address>`
- [ ] **manual** Real test submission: on-page confirmation, admin email, client auto-reply
- [ ] Mailbox for the notification address actually exists
- [ ] Meta descriptions staged (`launch.py seo`); confirm they render in `<head>`

## 6. Findability

- [ ] Static front page set (Settings → Reading) and permalinks set to Post name
- [ ] `/sitemap_index.xml` returns 200
- [ ] `llms.txt` uploaded to web root (see `reference/llms-template.txt`). REST cannot
      write root files, use the host file manager
- [ ] Schema type set for the business (Rank Math → Titles & Meta → Local SEO for
      brick-and-mortar)
- [ ] Search Console property added and sitemap submitted

## 7. Handover

- [ ] Publish drafts
- [ ] Purge host cache
- [ ] Rotate any credentials that were shared during the build
- [ ] Domain-dependent values listed for the move: absolute links, form confirmation
      redirects, schema `@id`, sitemap URLs, hardcoded hosts in scripts
- [ ] **manual** Settings → Reading → untick "Discourage search engines" (staging leaves
      `robots.txt` at `Disallow: /`)
- [ ] Tell the client which parts are static and what a content change requires
