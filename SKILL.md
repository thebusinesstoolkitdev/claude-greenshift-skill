---
name: greenlight-builder
description: >
  Build and launch complete WordPress sites on the Greenshift block builder (and the
  Greenlight FSE theme) from any design source — Figma, Paper/.pen, screenshots, sketches —
  entirely over the REST API. Covers design extraction, image optimisation and upload, a
  token-based stylebook, block generation, pages, FSE header/footer template parts, fluid
  responsive layout, WCAG/agent accessibility, and the launch stack (forms, SMTP, SEO).
  Triggers on: greenshift, greenlight theme, wpsoul, design to wordpress, figma to
  wordpress, paper to wordpress, build a wordpress site from a design, recreate this design
  in wordpress, gutenberg blocks from design.
---

# Greenlight / Greenshift site builder

Turn a design into a finished, launch-ready WordPress site without touching the block
editor. Everything — styles, pages, header, footer, forms, SEO — is pushed over REST, so
the whole build is scriptable, reviewable, and repeatable.

If a `greenshift-blocks` skill is available, read it first for block-format basics. This
skill covers the site-level pipeline and the API behaviour that is not documented anywhere.

## Three rules that cause most failures

1. **`"CSSRender": true` on every block with `styleAttributes`.** REST-pushed blocks never
   pass through the editor, so nothing compiles their CSS. Without this the page renders
   completely unstyled.
2. **Single-value `styleAttributes` only.** Server-side CSSRender mishandles multi-value
   responsive arrays — the mobile entry is dropped and mobile inherits desktop. Use
   `clamp()`/`min()` for fluid values and keep every breakpoint in a stylebook class.
3. **Declare custom attributes in the block JSON.** Any `data-*`, `aria-*` or `role` must
   appear in `dynamicAttributes` *and* the HTML, or Gutenberg fails validation, offers
   "Attempt recovery", and recovery strips them.

`scripts/gsblocks.py` enforces all three. `reference/troubleshooting.md` has the full
symptom-first list.

## Setup

`.env` in the project root:

```
WP_URL=https://site.com
WP_USER=admin@example.com
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx   # Users -> Profile -> Application Passwords
FIGMA_TOKEN=figd_...                            # Figma input only
```

Verify before building anything:

```python
from scripts.wp_api import WP
print(WP().check())   # expect is_admin True, greenshift True
```

Project layout: `input/` design refs · `assets/` optimised images · `output/` generated
block HTML · `reference/` node dumps and media map · `scripts/` generators.

Ask the host what it already provides. Managed WordPress usually covers caching, security
and backups — do not install plugins that duplicate them.

## Design sources

- **Figma** — REST API directly, no MCP needed. `GET /v1/files/{key}?depth=2` for the frame
  list, `/v1/files/{key}/nodes?ids=…` for full trees (pull every text string, font, colour
  and image fill), `/v1/images/{key}?ids=…&format=png&scale=2` to export assets. Header
  `X-Figma-Token`.
- **Paper (.pen)** — the Paper/pencil MCP tools. Read the schema first, then the node tree,
  then a screenshot for visual reference; export assets through the MCP. Never read `.pen`
  files directly.
- **Screenshots / sketches** — read the image, infer the structure, and confirm before
  building.

Always produce a **section map** (hero, features, CTA…) and get it approved before
generating. It is the cheapest place to catch a misread.

## Images

Export at 2x → convert to JPG q82 (keep PNG only for transparency) → cap width 1200, or
2000 for full-bleed backgrounds → upload via `POST /wp/v2/media` with `Content-Type` and
`Content-Disposition: attachment; filename="…"`. Record ids and URLs in
`reference/media-map.json`.

Set the site logo with `POST /wp/v2/settings {"site_logo": <id>}` **and set `alt_text` on
the attachment** — the header logo link has no other accessible name, and its absence is a
failed accessibility audit.

## Stylebook first, pages second

`POST /wp-json/greenshift/v1/global_settings` is the single source of truth for the design
system. Build it before generating pages so pages can simply reference classes.

| Key | Shape | Emitted as |
| --- | --- | --- |
| `variables` | `{"name","variable":"--x","variable_value"}` | `body { --x: … }` |
| `colours` | flat array of hex | editor palette, `--gs-color0..n` |
| `global_classes` | `{"value","label","css"}` | the CSS string verbatim (media queries allowed) |
| `elements` | `{"selector","css","admincss"}` | element styles; **prefix with `body`** or theme rules that load later win |

Merge semantics: each key you send **replaces** the stored array. Always read, merge
locally, then write — `WP.gs_upsert_classes()` and `scripts/stylebook.py push` do this.

`reference/starter-tokens.json` is a complete working system: colour, radius, focus-ring and
fluid type/spacing tokens; button, eyebrow, card, form and screen-reader classes; and the
layout classes below. Rename the `gt-` prefix per project if you like — just rename it
consistently.

Layout classes hold every breakpoint: `gt-grid-2` `gt-grid-3` `gt-grid-4` `gt-grid-even`
`gt-grid-split` `gt-footer-grid` `gt-form-row` `gt-section` `gt-container`.

**Gate the palette on contrast before you build on it.** `python scripts/check_contrast.py
--bg "#fbf6ec" --fg body:#8c8172 accent:#e27b4b` reports ratios and suggests passing
variants. Mid-tone brand colours routinely fail AA on light surfaces; fixing the token costs
one call, fixing it after the build costs a retrofit.

## Generating pages

Use `scripts/gsblocks.py` — `block()`, `image()`, `svg_icon()`, `section()`, `container()`,
`grid()`, `button()`, `heading()`, `eyebrow()`, `raw_html()`, `shortcode()`. See
`examples/` for two complete generators.

- Block ids: `gsbp-` + 7 chars, deterministic from a seed; `localId` identical; the id must
  appear in the HTML `class`.
- `--` cannot appear in an HTML comment, so CSS custom properties are escaped to
  `--` inside block JSON. Watch out for `re.sub` replacement strings containing
  `\u` — use a lambda.
- Headings carry margins and alignment only; size, weight and colour come from element
  styles. One `h1` per page, `h2` per section, `h3` for cards, and **never skip a level** —
  a section of `h3` cards needs an `h2` above it, visually hidden (`gt-sr-only`) if the
  design has no visible heading there.
- Eyebrows are `div`s, not headings. Content cards are `article`.

Push: `POST /wp/v2/pages {"title","slug","status":"draft","content":…,"template":"no-title"}`.
The `no-title` template stops the theme printing the page title as a second `h1`; confirm
the slug in `GET /wp/v2/templates`. After any content update clear stale editor CSS with
`POST /greenshift/v1/css_settings {"id":…,"css":""}` (`WP.update_page()` does it for you).

## Header and footer (FSE template parts)

`GET|POST /wp/v2/template-parts/{theme}//header` and `//footer`, payload `{"content"}`.

**Header: edit surgically, never rewrite.** Greenlight's header contains working Greenshift
navigation machinery — hamburger trigger, sliding mobile panel, menu-copy areas, generated
control ids (`gs_menu_XXXX`). Download the raw content and patch it: prepend a topbar, swap
the placeholder `<li>` items inside the menu `<ul>`, replace the demo CTA, restyle the
wrapper group. The mobile panel copies the desktop menu at runtime — leave it alone.

The theme's hamburger ships without an accessible name. Add `aria-label`, `aria-controls`
and `aria-expanded`, plus a small delegated script that flips `aria-expanded` and the label
when it toggles. `examples/generate_chrome.py` shows the exact patches.

**Footer: rewrite freely** with Greenshift elements on `gt-footer-grid`. Wrap link columns in
`<nav aria-label="…">`.

## Interactivity

Ship behaviour as a `core/html` script block using **event delegation on `document`** so it
survives re-saves and reordering. The editor canvas never runs these scripts — test on the
front end only.

To show/hide, set `el.style.display`. **Never use the `hidden` attribute**: block CSS with
`display:flex` beats `[hidden]`, so elements report themselves hidden while staying visible.
Verify with `offsetParent === null` or computed display — not with the property you just set.

Filter pattern that works: `button` chips with `aria-pressed`, a container with `role=group`
and a label, an `aria-live` region announcing the result count, and an empty-state message.
Card categories go in `data-*` attributes declared in the block JSON.

Client-side filtering suits a curated set. Only reach for posts + categories with a
Greenshift query grid when the client needs to add items themselves, and WooCommerce only
when they actually sell online. A custom post type is rarely the right first step.

## Accessibility and agent readiness

Treat these as build requirements, not a later pass:

- Contrast gated at the token level (above).
- Visible `:focus-visible` styling on every interactive element.
- A `prefers-reduced-motion` block that neutralises transitions and animations.
- Every control has an accessible name — icon-only links need `aria-label`, images inside
  links need real `alt`.
- State is exposed: `aria-expanded` on disclosure controls, `aria-pressed` on toggles.
- Landmarks are labelled: `<nav aria-label="Main">`, `<nav aria-label="Footer navigation">`.
- Form fields have real `<label>`s plus `autocomplete`; inputs are ≥16px so iOS does not zoom.
- Heading outline is continuous, one `h1` per page.
- `llms.txt` at the web root (`reference/llms-template.txt`) — REST cannot write root files,
  so upload it through the host file manager.

`python scripts/verify.py --all` checks the mechanical half of this list on live pages.

## Launch stack

`python scripts/launch.py plugins` installs Fluent Forms, FluentSMTP and Rank Math. Large
plugins often return HTTP 500 on install while the files land fine — re-read
`GET /wp/v2/plugins` and activate what is present rather than trusting the response.

**Forms** — `POST /fluentform/v1/forms` rejects payloads without one of its own template
keys, so duplicate the bundled demo form and overwrite its fields
(`python scripts/launch.py form "<Business>"`). Embed with the `[fluentform id="N"]`
shortcode inside a container carrying `gt-form-card` to inherit brand styling.

**Form settings are the classic footgun**: `POST /fluentform/v1/settings/{id}` *inserts* a
new row unless you pass `meta_id`. Duplicated rows mean duplicate emails or a confirmation
that will not change. Read first, pass the row id back.

`python scripts/launch.py emails <form_id> <address>` brands the on-page confirmation, the
admin notification (Reply-To set to the sender so replies just work) and a client
auto-reply, using table-based HTML that survives Gmail/Outlook/Apple Mail.

**SEO** — Rank Math does not expose `rank_math_*` meta over REST until its wizard has run,
but its default description template falls back to the post excerpt, which *is* a REST
field. Write excerpts. Two steps stay manual: the setup wizard, and Settings → Permalinks →
Save to flush rewrite rules (without it the sitemap 404s).

## Verification

1. `python scripts/verify.py --all` — heading outline, image alt and dimensions, accessible
   names, block CSS presence, undefined tokens.
2. `python scripts/stylebook.py verify` — tokens and classes actually reach the browser.
3. Browser at 375px — grids collapse, footer stacks, no horizontal overflow
   (`document.documentElement.scrollWidth <= innerWidth`).
4. Front-end click-through of anything interactive.

Two habits worth keeping: **verify what the user sees**, not what a DOM property claims; and
when a check disagrees with manual inspection, **suspect the check** — print the values it
compares before trusting its verdict.

Security plugins start returning 403 to scripted page fetches after repeated hits. Send a
browser `User-Agent` (verify.py does) or check in a browser. Authenticated REST calls are
unaffected. Managed hosts also proxy-cache the front end — append a unique query string
while testing and purge before a handover.

## Order of operations

1. `.env`, auth check, confirm what the host already provides
2. Extract the design → section map → approval
3. Contrast gate the palette → push the stylebook
4. Images: export, optimise, upload, logo + alt text
5. Generate and push pages as drafts
6. Header surgical patch, footer rewrite
7. `verify.py --all`, then the browser at 375px
8. Launch stack: plugins, form, emails, SEO, llms.txt
9. Work `reference/launch-checklist.md` and hand over the manual steps
