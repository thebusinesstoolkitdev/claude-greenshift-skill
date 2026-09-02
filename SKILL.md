---
name: greenlight
description: >
  Builds WordPress sites over the REST API, from a Figma file, a .pen file, screenshots or
  a sketch, without opening the block editor. It extracts the design, converts and uploads
  the images, pushes a token-based stylebook, generates Gutenberg blocks, and wires up the
  pages, the FSE header and footer, the contact form, SMTP and SEO. One set of generator
  calls emits either native WordPress core blocks or Greenshift element blocks.
  Use it whenever someone wants a WordPress page, section or whole site built from a
  design, or wants Gutenberg block markup written in code rather than clicked together in
  the editor. That includes the Greenlight theme, Greenshift, wpsoul, figma to wordpress,
  paper to wordpress, design to wordpress, "recreate this design in wordpress", "build the
  block markup for this section", and any scripted WordPress work over wp-json.
---


# Greenlight site builder

Turn a design into a finished, launch-ready WordPress site without touching the block
editor. Everything, styles, pages, header, footer, forms, SEO, is pushed over REST, so
the whole build is scriptable, reviewable, and repeatable.

## Two engines, one set of calls

`scripts/blocks.py` emits Gutenberg markup against either engine, from identical generator
code:

| | `greenshift` (default) | `core` |
|---|---|---|
| Emits | `wp:greenshift-blocks/element` | `wp:group`, `wp:heading`, `wp:paragraph`, `wp:list`, `wp:image`, `wp:buttons` |
| Needs | Greenshift plugin | nothing |
| Styling | per-block CSS compiled server-side | stylebook classes and theme.json |
| Block id class | `gsbp-xxxxxxx` (Greenshift targets it) | `gl-xxxxxxx` |

Pick with `set_backend('core')` or `GREENLIGHT_BACKEND=core`. Greenshift stays the default
because it is what existing builds use.

**The difference that matters: core blocks cannot carry arbitrary CSS.** The core backend
translates the spacing, colour and typography subset core genuinely supports, and refuses
anything else with a message telling you to put it in a stylebook class. That is already
what this skill tells you to do with breakpoints, so a generator written to the house style
ports with little friction, and one that scatters inline CSS will tell you exactly where.

A few things have no core equivalent and raise rather than degrade silently: raw `<svg>`
icons, background images on sections, and arbitrary tags like `<nav>`. Each error names the
alternative. Needing several of them is a good reason to stay on Greenshift.

If a `greenshift-blocks` skill is available, read it first for block-format basics. This
skill covers the site-level pipeline and the API behaviour that is not documented anywhere.
`reference/upstream-block-spec.md` is the block format as WPsoul specifies it, with every
place this skill deliberately diverges called out, read it before changing anything about
block emission. `reference/site-conventions.md` covers the decisions that are not
Greenshift-specific, typography measure, link and title hygiene, safe updates, handover. Read it before writing
page content; most of it is invisible until it is expensive.

## Four rules that cause most failures

Rules 1-3 are Greenshift-backend specific. Rule 4 applies to both.

1. **`"CSSRender": true` on every block with `styleAttributes`.** REST-pushed blocks never
   pass through the editor, so nothing compiles their CSS. Without this the page renders
   completely unstyled. Upstream instead writes one CSS string to the `_gspb_post_css` post
   meta for pages and reserves `"CSSRender":"1"` for patterns and templates; this skill uses
   CSSRender everywhere and clears that meta, so a regenerated page cannot inherit stale CSS.
   Both work, never mix them on one page. See `reference/upstream-block-spec.md`.
2. **Single-value `styleAttributes` only.** The format is a four-value responsive array,
   `["desktop","tablet","mobile_landscape","mobile_portrait"]`, with fewer values applying
   upward. Multi-value arrays pushed over REST were observed dropping the smallest entry so
   mobile inherited desktop, so this skill sends one value and keeps every breakpoint in a
   stylebook class. Use `clamp()`/`min()` for fluid values.
3. **Every HTML attribute must be reachable from the block JSON.** Not just `data-*`,
   `aria-*` and `role`: `fetchpriority`, `decoding`, `type` and anything else you write
   into the tag has to appear in `dynamicAttributes` too. Greenshift renders `class`,
   `href`, `src`, `alt`, `title`, `width`, `height`, `loading`, `target`, `rel` and the
   media attributes from its own keys, so those are already covered. Everything else is
   undeclared markup: Gutenberg fails validation, offers "Attempt recovery", and recovery
   deletes the attribute. Nothing warns you, and `verify.py` passes, because the page
   renders correctly until someone opens it in the editor.

   **An `id` is the `anchor` key, never an attribute.** Pass `anchor='weddings'` and the
   block emits `id="weddings"`. A raw `id` is the most costly version of this bug because
   recovery strips it and every anchor link pointing at that section silently dies.
   `blocks.py` refuses a raw `id` and declares everything outside the rendered set.
4. **Build content from element blocks, never raw HTML.** A `core/html` block is opaque:
   the client cannot edit a word of it in the editor, it ignores the stylebook so it drifts
   the moment a token or layout class changes, and every check in this skill skips straight
   past it. The commonest version of this mistake is hand-writing a grid of cards as one
   slab of markup. `core/html` is for scripts, JSON-LD and shortcodes. Everything else is
   `block()`, `grid()`, `heading()`, `image()`, `section()`.

`scripts/blocks.py` enforces all four, `raw_html()` raises if it is handed content-shaped
markup. `reference/troubleshooting.md` has the full symptom-first list.

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
and backups, do not install plugins that duplicate them.

## Design sources

- **Figma**. REST API directly, no MCP needed. `GET /v1/files/{key}?depth=2` for the frame
  list, `/v1/files/{key}/nodes?ids=…` for full trees (pull every text string, font, colour
  and image fill), `/v1/images/{key}?ids=…&format=png&scale=2` to export assets. Header
  `X-Figma-Token`.
- **Paper (.pen)**, the Paper/pencil MCP tools. Read the schema first, then the node tree,
  then a screenshot for visual reference; export assets through the MCP. Never read `.pen`
  files directly.
- **Screenshots / sketches**, read the image, infer the structure, and confirm before
  building.

Always produce a **section map** (hero, features, CTA…) and get it approved before
generating. It is the cheapest place to catch a misread.

## Layout gotcha: core's flow margin

WordPress core emits `:root :where(.is-layout-flow) > * { margin-block-start: 1.6rem }`.
Every top-level section after the first inherits 25.6px of margin, which shows up as a
pale seam between full-bleed colour bands. Sections should carry their rhythm as padding,
so zero the margin with a `body`-prefixed selector in the stylebook:

```css
body .is-layout-flow > * { margin-block-start: 0; }
```

Specificity 0,1,1 beats core's 0,1,0 because `:where()` contributes nothing, so this needs
no `!important`. Any design with adjacent full-width bands hits this.

## Fonts

Uploading to the WordPress Font Library is only half the job. WordPress emits `@font-face`
only for families **activated** on the global-styles record
(`settings.typography.fontFamilies`). An installed but unactivated family falls back to a
system font with no error in any log, and every check in this skill still passes.

```
POST /wp/v2/font-families                      # family record
POST /wp/v2/font-families/{id}/font-faces      # one per weight and style, woff2
POST /wp/v2/global-styles/{id}                 # activate under settings.typography
```

Self-host rather than linking Google's CDN. Then assert, because this fails silently:
count `@font-face` blocks in the rendered page and check it equals the number of faces you
activated, and check `fonts.googleapis.com` and `fonts.gstatic.com` appear zero times.

## Images

Export at 2x → convert to JPG q82 (keep PNG only for transparency) → cap width 1200, or
2000 for full-bleed backgrounds → upload via `POST /wp/v2/media` with `Content-Type` and
`Content-Disposition: attachment; filename="…"`. Record ids and URLs in
`reference/media-map.json`.

Set the site logo with `POST /wp/v2/settings {"site_logo": <id>}` **and set `alt_text` on
the attachment**, the header logo link has no other accessible name, and its absence is a
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
locally, then write, `WP.gs_upsert_classes()` and `scripts/stylebook.py push` do this.

**On the `core` backend there is no Greenshift to hold the classes**, but the markup still
references them, so they have to be defined somewhere or the page ships unstyled. Same spec,
rendered as CSS onto the FSE global-styles record:

```
python scripts/stylebook.py push reference/starter-tokens.json --core
python scripts/stylebook.py css  reference/starter-tokens.json > stylebook.css   # or paste
```

The starter system comes out around 9KB of CSS. That record is native to FSE themes and
survives theme updates, which makes it the closest equivalent to a Greenshift global class.

`reference/starter-tokens.json` is a complete working system: colour, radius, focus-ring and
fluid type/spacing tokens; button, eyebrow, card, form and screen-reader classes; and the
layout classes below. Rename the `gt-` prefix per project if you like, just rename it
consistently.

Layout classes hold every breakpoint: `gt-grid-2` `gt-grid-3` `gt-grid-4` `gt-grid-even`
`gt-grid-split` `gt-footer-grid` `gt-form-row` `gt-section` `gt-container`.

**Every prose class carries a `max-width`.** `gt-lead` and `gt-body-copy` cap at 68-72ch.
Without it a class looks right inside a two-column split and runs 180 characters the first
time it is used full-width, the page reads as unstyled and the missing property is the last
thing anyone suspects.

**Prune on push.** A class you delete locally stays on the server, because the push replaces
the array it sends rather than diffing it. Read the stored classes, keep anything outside
your prefix, and drop prefixed classes you no longer define.

**Read the theme's own tokens before you design any.** The theme already emits a large
set of custom properties, and building a parallel system alongside them guarantees drift:
a container width that disagrees with the theme's, a radius token its own buttons ignore.

```python
import re, urllib.request
html = urllib.request.urlopen(WP().url).read().decode()
print(sorted(set(re.findall(r'(\-\-wp\-\-[a-z0-9-]+)\s*:', html))))
```

Then consume what exists, define what the theme references but leaves undefined, and
invent only what is genuinely specific to this design. **Read the install, not the docs.**
A live Greenlight 2.1 emits 81 properties: 20 font sizes, 12 spacing steps, 11 shadows,
`--wp--style--global--content-size` and `--wp--style--global--wide-size`, and **zero**
border-radius or size customs, whichever version the documentation describes.

**Gate the palette on contrast before you build on it.** `python scripts/check_contrast.py
--bg "#fbf6ec" --fg body:#8c8172 accent:#e27b4b` reports ratios and suggests passing
variants. Mid-tone brand colours routinely fail AA on light surfaces; fixing the token costs
one call, fixing it after the build costs a retrofit.

## Images

**Every raster image ships as WebP. No exceptions for PNG or JPEG.** Image weight is
normally the largest single component of a page; WebP is 25-35% smaller than JPEG at the
same quality and dramatically smaller than PNG. `wp_api.upload_media()` converts anything
raster it is handed, so a stray PNG cannot reach the media library by any route, including
a one-off manual upload from a script. SVG passes through untouched, GIF passes through
because converting kills the animation, and `keep_format=True` exists for a genuine
third-party requirement.

```
python scripts/prep_images.py build            # input/raw -> assets/, all WebP, q82
python scripts/prep_images.py build --max 1600 # cap the long edge
python scripts/prep_images.py upload           # upload + write reference/media-map.json
python scripts/prep_images.py audit            # non-WebP already in the library
```

Run `build` before uploading so the sizing and quality are deliberate rather than the
conversion defaults. **Nothing is ever upscaled**, a source smaller than its display slot
is re-encoded at its own size, because stretching it adds bytes and removes detail.

**Each image is encoded both lossy and lossless and the smaller one wins.** A fixed lossy
quality is the obvious default and it is wrong for a whole class of images every site has:
logos, screenshots, diagrams, flat illustrations. Lossy encoders spend bytes on the hard
edges they cannot represent, so a 79kB PNG logo comes back as a 153kB WebP, a regression
wearing the costume of an optimisation. Photographs go the other way and compress far
better lossy. Trying both costs one extra encode and removes the guesswork; the build
prints which mode won and warns if any output is still larger than its source.

Alt text is required at upload, not added later: `upload` refuses any image without an
`alt` in `media-map.json` (shape in `reference/media-map-template.json`) and tells you which. Set it on the attachment (`alt_text`), not
only in the block, so the media library stays correct.

Emit `srcset`/`sizes` on anything that spans a responsive slot, `loading="lazy"` everywhere
except the LCP image, and `fetchpriority="high"` on that one. Always `width`/`height` to
reserve space.

`prep_images.py audit` and `verify.py --all` both fail on a non-WebP raster image, so this
stays enforced after handover rather than only at build time.

## Generating pages

Use `scripts/blocks.py`, `block()`, `image()`, `svg_icon()`, `section()`, `container()`,
`grid()`, `button()`, `heading()`, `eyebrow()`, `raw_html()`, `shortcode()`. See
`examples/` for two complete generators.

- Block ids: `gsbp-` + 7 chars, deterministic from a seed; `localId` identical; the id must
  appear in the HTML `class`.
- `--` cannot appear in an HTML comment, so CSS custom properties are escaped to
  `--` inside block JSON. Watch out for `re.sub` replacement strings containing
  `\u`, use a lambda.
- Headings carry margins and alignment only; size, weight and colour come from element
  styles. One `h1` per page, `h2` per section, `h3` for cards, and **never skip a level**, a section of `h3` cards needs an `h2` above it, visually hidden (`gt-sr-only`) if the
  design has no visible heading there.
- Eyebrows are `div`s, not headings. Content cards are `article`.

**Raw HTML is a last resort, not a shortcut.** `raw_html()` exists for scripts, JSON-LD,
stylesheets and shortcodes. It raises if you hand it content-shaped markup, because content
in a `core/html` block:

- cannot be edited in the block editor, which defeats the point of handing over a block site
- takes inline styles rather than stylebook classes, so it ignores tokens and every
  responsive breakpoint the layout classes carry
- is invisible to `verify.py` and the block checks, no heading-order, alt-text or contrast
  coverage
- silently stops matching the rest of the site the first time a global class changes

A grid of cards is `grid()` wrapping one `block(..., 'article')` per card, each holding a
`heading()` and a `block(..., 'p')`. It is more lines than a slab of markup and it is the
deliverable the client actually bought. If some third-party embed genuinely has to stay raw,
pass `raw_html(markup, reason='…')` and say why in the reason.

**Never send `status` on a content update.** Send it when creating a page, and when
deliberately changing state, never on every push. A helper that always sends
`status:"draft"` unpublishes the live site the first time it runs against production, and a
REST write can flip a draft to published as a side effect. Read the statuses back after any
bulk update.

Push: `POST /wp/v2/pages {"title","slug","status":"draft","content":…,"template":"no-title"}`
to create; `{"content":…}` alone to update.
The `no-title` template stops the theme printing the page title as a second `h1`; confirm
the slug in `GET /wp/v2/templates`. After any content update clear stale editor CSS with
`POST /greenshift/v1/css_settings {"id":…,"css":""}` (`WP.update_page()` does it for you).

## Header and footer (FSE template parts)

`GET|POST /wp/v2/template-parts/{theme}//header` and `//footer`, payload `{"content"}`.

**Header: edit surgically, never rewrite.** Greenlight's header contains working Greenshift
navigation machinery, hamburger trigger, sliding mobile panel, menu-copy areas, generated
control ids (`gs_menu_XXXX`). Download the raw content and patch it: prepend a topbar, swap
the placeholder `<li>` items inside the menu `<ul>`, replace the demo CTA, restyle the
wrapper group. The mobile panel copies the desktop menu at runtime, leave it alone.

The theme's hamburger ships without an accessible name. Add `aria-label`, `aria-controls`
and `aria-expanded`, plus a small delegated script that flips `aria-expanded` and the label
when it toggles. `examples/generate_chrome.py` shows the exact patches.

**Footer: rewrite freely** with Greenshift elements on `gt-footer-grid`. Wrap link columns in
`<nav aria-label="…">`.

## Interactivity

Ship behaviour as a `core/html` script block using **event delegation on `document`** so it
survives re-saves and reordering. The editor canvas never runs these scripts, test on the
front end only.

To show/hide, set `el.style.display`. **Never use the `hidden` attribute**: block CSS with
`display:flex` beats `[hidden]`, so elements report themselves hidden while staying visible.
Verify with `offsetParent === null` or computed display, not with the property you just set.

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
- Every control has an accessible name, icon-only links need `aria-label`, images inside
  links need real `alt`.
- State is exposed: `aria-expanded` on disclosure controls, `aria-pressed` on toggles.
- Landmarks are labelled: `<nav aria-label="Main">`, `<nav aria-label="Footer navigation">`.
- Form fields have real `<label>`s plus `autocomplete`; inputs are ≥16px so iOS does not zoom.
- Heading outline is continuous, one `h1` per page.
- `llms.txt` at the web root (`reference/llms-template.txt`). REST cannot write root files,
  so upload it through the host file manager.

`python scripts/verify.py --all` checks the mechanical half of this list on live pages.

## Launch stack

`python scripts/launch.py plugins` installs Fluent Forms, FluentSMTP and Rank Math. Large
plugins often return HTTP 500 on install while the files land fine, re-read
`GET /wp/v2/plugins` and activate what is present rather than trusting the response.

**Forms**, `POST /fluentform/v1/forms` rejects payloads without one of its own template
keys, so duplicate the bundled demo form and overwrite its fields
(`python scripts/launch.py form "<Business>"`). Embed with the `[fluentform id="N"]`
shortcode inside a container carrying `gt-form-card` to inherit brand styling.

**Fields are writable, but only under the right key.** `formFields` works. `form_fields`
is accepted, returns success, and changes nothing, which reads exactly like the API
refusing field writes. It is not refusing. `fluentform/v1/forms` also returns a paginated
envelope (`{current_page, per_page, data:[…]}`), so iterating the response as a list
raises `TypeError: string indices must be integers`. `WP.ff_forms()` unwraps it.

**Form settings are the classic footgun**: `POST /fluentform/v1/settings/{id}` *inserts* a
new row unless you pass `meta_id`. Duplicated rows mean duplicate emails or a confirmation
that will not change. Read first, pass the row id back.

`python scripts/launch.py emails <form_id> <address>` brands the on-page confirmation, the
admin notification (Reply-To set to the sender so replies just work) and a client
auto-reply, using table-based HTML that survives Gmail/Outlook/Apple Mail.

**SEO**. Rank Math does not expose `rank_math_*` meta over REST until its wizard has run,
but its default description template falls back to the post excerpt, which *is* a REST
field. Write excerpts. Two steps stay manual: the setup wizard, and Settings → Permalinks →
Save to flush rewrite rules (without it the sitemap 404s).

## Verification

1. `python scripts/verify.py --all`, heading outline, image alt and dimensions, accessible
   names, block CSS presence, undefined tokens.
2. `python scripts/check_links.py`, internal links, in-page anchors, links to drafts, and
   whether the main nav is identical across pages. `verify.py` reads one page at a time and
   never follows a link, so every cross-page link defect survives it.
3. `python scripts/stylebook.py verify`, tokens and classes actually reach the browser.
4. Browser at 375px, grids collapse, footer stacks, no horizontal overflow
   (`document.documentElement.scrollWidth <= innerWidth`).
5. Front-end click-through of anything interactive.

Two habits worth keeping: **verify what the user sees**, not what a DOM property claims; and
when a check disagrees with manual inspection, **suspect the check**, print the values it
compares before trusting its verdict.

Security plugins start returning 403 to scripted page fetches after repeated hits. Send a
browser `User-Agent` (verify.py does) or check in a browser. Authenticated REST calls are
unaffected. Managed hosts also proxy-cache the front end, append a unique query string
while testing and purge before a handover.

## Order of operations

1. `.env`, auth check, confirm what the host already provides
2. Extract the design → section map → approval
3. Contrast gate the palette → push the stylebook
4. Images: export → `prep_images.py build` (WebP) → `upload`, logo + alt text
5. Generate and push pages as drafts
6. Header surgical patch, footer rewrite
7. `verify.py --all`, `check_links.py`, then the browser at 375px
8. Launch stack: plugins, form, emails, SEO, llms.txt
9. Work `reference/launch-checklist.md` and hand over the manual steps
