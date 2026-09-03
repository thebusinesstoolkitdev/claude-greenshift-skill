---
name: greenlight
description: >
  Builds WordPress sites over the REST API, from a Figma file, a .pen file, screenshots or
  a sketch, without opening the block editor. It extracts the design, converts and uploads
  the images, pushes a token-based stylebook, generates Gutenberg blocks, and wires up the
  pages, the FSE header and footer, the contact form, SMTP and SEO. One set of generator
  calls emits either native WordPress core blocks or GreenLight element blocks.
  Use it whenever someone wants a WordPress page, section or whole site built from a
  design, or wants Gutenberg block markup written in code rather than clicked together in
  the editor. That includes the GreenLight builder, GreenShift, wpsoul, figma to wordpress,
  paper to wordpress, design to wordpress, "recreate this design in wordpress", "build the
  block markup for this section", and any scripted WordPress work over wp-json.
---


# GreenLight site builder

Turn a design into a finished, launch-ready WordPress site without touching the block
editor. Everything, styles, pages, header, footer, forms, SEO, is pushed over REST, so
the whole build is scriptable, reviewable, and repeatable.

## Two engines, one set of calls

`scripts/blocks.py` emits Gutenberg markup against either engine, from identical generator
code:

| | `greenshift` (default) | `core` |
|---|---|---|
| Emits | `wp:greenshift-blocks/element` | `wp:group`, `wp:heading`, `wp:paragraph`, `wp:list`, `wp:image`, `wp:buttons` |
| Needs | GreenLight builder | nothing |
| Styling | per-block CSS compiled server-side | stylebook classes and theme.json |
| Block id class | `gsbp-xxxxxxx` (GreenLight targets it) | `gl-xxxxxxx` |

Pick with `set_backend('core')` or `GREENLIGHT_BACKEND=core`. GreenLight stays the default
because it is what existing builds use.

**The difference that matters: core blocks cannot carry arbitrary CSS.** The core backend
translates the spacing, colour and typography subset core genuinely supports, and refuses
anything else with a message telling you to put it in a stylebook class. That is already
what this skill tells you to do with breakpoints, so a generator written to the house style
ports with little friction, and one that scatters inline CSS will tell you exactly where.

A few things have no core equivalent and raise rather than degrade silently: raw `<svg>`
icons, background images on sections, and arbitrary tags like `<nav>`. Each error names the
alternative. Needing several of them is a good reason to stay on GreenLight.

If a `greenshift-blocks` skill is available, read it first for block-format basics. This
skill covers the site-level pipeline and the API behaviour that is not documented anywhere.
**Before you change anything about block emission, read the specification itself.**

```
python scripts/upstream.py sync              # clone it, pin the commit
python scripts/upstream.py show CSSRender    # grep the real docs
python scripts/upstream.py show -f validate-styles.md
python scripts/upstream.py check             # has upstream moved since the pin?
```

That clones WPsoul's `greenlight-vibe` into `reference/upstream/` so you read primary text.
This is not optional caution. An earlier version of this file described the format from web
summaries. The summaries got `CSSRender` wrong, inverted the pages-versus-templates
contract, omitted `dynamicGClasses` and the `stylemanager` block completely, and listed a
file that does not exist while missing three that do. A summary of a specification is not a
specification.

`reference/upstream-block-spec.md` is now only a divergence register: where this skill
departs from the spec, and why. The spec itself lives upstream and is fetched on demand.

block emission. `reference/site-conventions.md` covers the decisions that are not
GreenLight-specific, typography measure, link and title hygiene, safe updates, handover. Read it before writing
page content; most of it is invisible until it is expensive.

## Four rules that cause most failures

Rules 1-3 are GreenLight-backend specific. Rule 4 applies to both.

1. **CSS delivery depends on where the markup is going, and the two paths never mix.**
   Upstream splits it (`instructions/validate-styles.md`, its `SKILL.md:259`):

   | Target | Contract |
   |---|---|
   | patterns, template parts, templates | `"CSSRender": "1"` on every block with `styleAttributes` or `dynamicGClasses` |
   | pages, posts, custom post types | **no CSSRender**; the page's whole CSS goes into the `_gspb_post_css` meta as one string |

   The value is the string `"1"`, not a boolean. A boolean satisfies the PHP renderer,
   which is exactly why the wrong value survived here unnoticed. REST-pushed blocks never
   pass through the editor, so nothing compiles their CSS; pick the wrong half of this
   contract and the page renders unstyled.

   `blocks.set_target('page')` omits CSSRender, and `blocks.compile_css(markup)` builds the
   string for `WP.set_post_css()`. Default is `template`, correct for the header and footer,
   which are template parts.
2. **Responsive arrays work over REST; the constraint is who compiles them.**
   `styleAttributes` values are four-entry arrays,
   `["desktop","tablet","mobile_landscape","mobile_portrait"]`, fewer entries applying
   upward. Verified against GreenLight 2.1 / gl-page-builder 3.3.7: every shape (1 to 4
   entries, `null` or `""` gaps, `gridTemplateColumns`) round-trips intact and the PHP
   renderer emits `max-width` rules at 991.98px, 767.98px and 575.98px, smallest entry
   included. An earlier version of this skill banned multi-value arrays on one
   unreproduced observation; `python scripts/probe_responsive.py` re-runs the check
   against any site before you trust either claim on a new plugin version.

   What still constrains you: on a page target nothing server-side compiles them, so
   `blocks.compile_css()` does, mirroring those breakpoints. On the core backend there are
   no per-block breakpoints at all, so a multi-value array raises and the breakpoint goes
   in a stylebook class. Shared layout (grids, footer columns) stays in a stylebook class
   because it is shared, not because arrays are unsafe.
3. **Every HTML attribute must be reachable from the block JSON.** Not just `data-*`,
   `aria-*` and `role`: `fetchpriority`, `decoding`, `type` and anything else you write
   into the tag has to appear in `dynamicAttributes` too. GreenLight renders `class`,
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
| `global_classes` | `{"value","label","css"}` in the spec; `stylebook.py` fills in `type`, `attributes`, `originalID`, `originalBlock`, `tag`, `selectors` | the CSS string verbatim (media queries allowed) |
| `elements` | list of `{"selector","css"}` in the spec, emitted as one `<prefix>-elements` class | element styles; **prefix with `body`** or theme rules that load later win |

**The Stylebook admin screen needs the full class shape.** It groups classes by
`originalBlock` and builds a heading from it; an entry without the key crashes the whole
screen with "This block has encountered an error and cannot be previewed", while the front
end renders the same entry fine. `stylebook.py push` writes the shape the screen itself
creates and repairs existing entries on the next push. Its `elements` model is an object
keyed by tag with `styleAttributes` it regenerates CSS from, which free-form element CSS
does not fit, so the spec's `elements` list becomes a class and renders identically.

Merge semantics: each key you send **replaces** the stored array. Always read, merge
locally, then write, `WP.gs_upsert_classes()` and `scripts/stylebook.py push` do this.

**The stylebook prints before the theme's global styles**, so a class rule loses every
equal-specificity tie to theme.json that a page stylesheet (printed last) would have won.
Prefix class selectors with `body` the same way as element styles, `body .gt-card{…}`,
0,1,1 beats 0,1,0 with no `!important`. Keep rules in the order the design wrote them:
grouping every rule under its first class silently reorders two equal-specificity rules
(`.head .small` before `.dark .small` becomes the reverse) and flips a colour. Moving a
site's CSS out of a page into the stylebook was verified with a computed-style diff of
every element on the rendered page, which is the only check that catches this.

**On the `core` backend there is no GreenLight to hold the classes**, but the markup still
references them, so they have to be defined somewhere or the page ships unstyled. Same spec,
rendered as CSS onto the FSE global-styles record:

```
python scripts/stylebook.py push reference/starter-tokens.json --core
python scripts/stylebook.py css  reference/starter-tokens.json > stylebook.css   # or paste
```

The starter system comes out around 9KB of CSS. That record is native to FSE themes and
survives theme updates, which makes it the closest equivalent to a GreenLight global class.

`reference/starter-tokens.json` is a complete working system: colour, radius, focus-ring and
fluid type/spacing tokens; button, eyebrow, card, form and screen-reader classes; the
layout classes below; and a **base layer** in `elements` (box-sizing, reduced-motion-aware
smooth scroll, body full-height + `overflow-x:clip`, link colour and an external-link arrow
indicator on text links only, paragraph rhythm) plus `.h1`-`.h6` heading look-alike classes
and a `.hidden-accessible` screen-reader-only class. Those are the global rules that cannot
be drawn in a design and belong site-wide, authored once here, not per block. Rename the `gt-` prefix per project if you like, just rename it
consistently.

**Colours are role tokens, not colour names.** `primary` / `primary-dark`, `secondary` /
`secondary-dark`, `accent`, `surface` / `surface-alt`, `text` / `text-muted`, `focus`. A
rebrand is then a value change; no generator, class or page mentions a hue. Keep the
`-text` variants (`accent-text`, `secondary-text`): they exist because the fill colour
fails AA as text, and a role name must not hide that. Two tints of a role are fine as
`-light` / `-dark`; at three or more switch to a numeric scale (`secondary-100` …
`secondary-900`) or the names stop meaning anything. With `--theme`, `primary` can alias
straight onto the theme's own `brand` preset via `map --apply`.

**Register the tokens with the theme, not beside it.** Upstream prefers the theme's own
`--wp--preset--*` and `--wp--custom--*` variables to a parallel token set, because two
systems drift. `push --theme` does both: every variable carries a `kind` (`color`,
`font-size`, `spacing`, `font-family`, `custom`) and is written as a theme.json preset of
that kind on the user global-styles record, then the stylebook variable is rewritten to
alias it, `--gt-primary: var(--wp--preset--color--gt-primary)`. Generators keep the `gt-`
names; the theme owns the values, the site editor shows them, and core blocks can pick
them from the preset pickers. A token that already exists in the theme under another name
gets an `alias` instead of a new preset; `stylebook.py map --apply` fills those in wherever
the values match.

```
python scripts/stylebook.py map  reference/starter-tokens.json --apply   # reuse theme presets
python scripts/stylebook.py push reference/starter-tokens.json --theme   # presets + aliased stylebook
python scripts/stylebook.py remove reference/starter-tokens.json         # retire the lot
```

**The theme's own palette is replaceable too.** The Stylebook's "Global Color Presets",
the editor pickers and GreenLight's own CSS (`var(--wp--preset--color--brand)`) read the
palette at the *theme* origin, which custom presets never touch. A colour token that
carries `theme_slug` (`"theme_slug": ["brand"]`, or several slots) has its value written
into those slots on the user global-styles record by `push --theme`, the way GreenLight's
onboarding sets its brand colour. Slot slugs never change, so nothing in the theme
dereferences a missing variable, and unmapped slots keep the theme value. The starter
tokens bind `primary` → `brand`, `surface` → `background`, `surface-alt` → `card-base`,
`text` → `textcolor`, `heading`, `card-text`, `text-muted` → `lightgrey`. If the site already
overrides the theme palette (GreenLight's onboarding does), that list is the base and only
the bound slots change. `push` prints every slot it changes; `remove` leaves them, put the
old values back in Appearance → Editor → Styles if wanted.

Two things WordPress does on the way that will bite a hand-written alias: preset slugs and
`settings.custom` keys are kebab-cased before the variable is emitted, so `gt-h1` is
`--wp--preset--font-size--gt-h-1`, and each of `settings` and `styles` on the record is
replaced whole on write. `stylebook.py` mirrors both; `verify` reports any alias whose
target the page never defines.

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
A live GreenLight 2.1 emits 81 properties: 20 font sizes, 12 spacing steps, 11 shadows,
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

## The documented section shell

A full-width section with centred content has a prescribed structure. `section()` and
`container()` emit it:

```html
<section class="wp-section alignfull" data-type="section-component">
  <div class="wp-content-wrap" data-type="content-area-component">…</div>
</section>
```

Keep the `alignfull` class, `var(--wp--style--global--wide-size, 1200px)` for the inner
width, and `var(--wp--spacing--side, min(3vw, 20px))` for side padding. Padding top and
bottom are yours; those three are not. Inventing your own section class instead is what
produces inter-section seams and a width that disagrees with the theme.

## Where a page's CSS lives

Three mechanisms, and picking the wrong one is the most common way to ship an unstyled page.

| Scope | Mechanism |
|---|---|
| site-wide tokens and shared classes | the stylebook (`global_settings`), or the FSE global-styles record on the core backend |
| one page's own classes | a **stylemanager** block: `style_manager(seed, classes={'home-hero': '.home-hero{…}'})`, emitting `isVariation:"stylemanager"` with `dynamicGClasses` in the converter's shape |
| a page's compiled block styles | `_gspb_post_css`, written by `WP.set_post_css()` from `compile_css()`, which folds the stylemanager's CSS in too |

What the PHP renderer behind `CSSRender` actually emits, probed on a live install: plain
`styleAttributes` properties (responsive arrays included), `dynamicGClasses[].css` and
`dynamicGClasses[].selectors[].css`. Nothing else. `customCss` on a stylemanager and
`customCSS_Extra` anywhere are compiled by the editor's JavaScript only, so on a template
target they never reach the page; `style_manager()` refuses `custom_css` there and
`check_blocks.py` flags both. A template part's class-less CSS belongs in the stylebook,
which is site-wide like the part itself. On a page target `compile_css()` includes them,
matching what an editor save would have written.

**Never add CSSRender to a block you did not author.** The theme's own blocks ship
`styleAttributes` next to already-compiled `inlineCssStyles`. Adding CSSRender re-emits the
raw values, which override the compiled rules. Doing this to a GreenLight header turns the
hidden mobile panel into a fixed full-height overlay across the whole site. The rule
"CSSRender on anything with styleAttributes" applies to your blocks only.

**`update_page()` clears `_gspb_post_css` by default.** That is correct on the CSSRender
path and destructive on the page path, where the field *is* the stylesheet. Pass
`clear_css=False` when you are about to call `set_post_css()`.

## Generating pages

Use `scripts/blocks.py`, `block()`, `image()`, `svg_icon()`, `section()`, `container()`,
`grid()`, `button()`, `heading()`, `eyebrow()`, `style_manager()`, `raw_html()`,
`shortcode()`. See `examples/` for two complete generators.

**One finished HTML file in hand? Use upstream's converter instead.** Hand-emitting from
Python suits many pages built from structured data. For a single design that already
exists as clean HTML, WPsoul's `convert.js` maps every element, files the `<style>` into a
stylemanager block, and `deconvert.js` brings it back for editing. `scripts/convert_html.py`
wraps it with this skill's delivery contract:

```
python scripts/convert_html.py input/home.html -o output/home.html --target page
python scripts/convert_html.py input/home.html --target page --publish "Home" --slug home
python scripts/convert_html.py input/promo.html -o output/promo.html --target template
```

It escapes `--` in the block JSON, sets `CSSRender` per target, compiles the page CSS (or
ships the original stylesheet with `--raw-css`), runs `check_blocks.py`, and reports what
the converter changed: a rule is filed under the first class in its selector and the
compound before it is dropped (`body.dark .title` becomes `.dark .title`), and a rule with
no class at all lands in `customCss`, which never renders on a template target.

- Block ids: `gsbp-` + 7 chars, deterministic from a seed; `localId` identical; the id must
  appear in the HTML `class`.
- `--` cannot appear in an HTML comment, so CSS custom properties are escaped to
  `--` inside block JSON. Watch out for `re.sub` replacement strings containing
  `\u`, use a lambda.
- Headings carry margins and alignment only; size, weight and colour come from element
  styles. One `h1` per page, `h2` per section, `h3` for cards, and **never skip a level**, a section of `h3` cards needs an `h2` above it, visually hidden (`gt-sr-only`) if the
  design has no visible heading there.
- Eyebrows are `div`s, not headings. Content cards are `article`.
- `className` goes in the block JSON **and** the HTML `class` attribute. `blocks.py` does
  both; hand-written markup that only sets one will not survive an editor round trip.
- `type`, `name`, `placeholder` and `required` on a form control belong in
  `formAttributes`, not in the main JSON and not in `dynamicAttributes`.
- Class and id prefixes are **four characters minimum**. This skill's own `gt-` predates
  that rule; pick a real project prefix (`ketup-`, `booz-`) for anything page-specific.
- No `:root` variables and no styles on `body` or `*` in page CSS. Variables belong on a
  parent block's class. The stylebook is the exception and a deliberate one: it is the
  global layer, and `global-settings.md` expects `:root`-style declarations to be extracted
  into it rather than left in the page.

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

`GET|POST /wp/v2/template-parts/{theme}//{slug}`, payload `{"content"}`. Do not assume the
slugs: `WP.get_template_part(area='header')` reads `GET /wp/v2/template-parts`, picks the
part whose `area` matches (a customised copy over the theme file), and works on any FSE
theme. `WP.set_template_part(area='footer', content=…)` writes the same way.

Which of the two treatments a header gets is decided by what is in it, not by the theme's
name: `blocks.has_greenshift_blocks(raw)`.

**A GreenLight header: edit surgically, never rewrite.** GreenLight's header contains working
GreenLight navigation machinery, hamburger trigger, sliding mobile panel, menu-copy areas,
generated control ids (`gs_menu_XXXX`). Download the raw content and patch it: prepend a
topbar, swap the placeholder `<li>` items inside the menu `<ul>`, replace the demo CTA,
restyle the wrapper group. The mobile panel copies the desktop menu at runtime, leave it
alone.

**Any other header** (core navigation block, another theme) has no machinery to protect.
Rewrite it like the footer, keeping the theme's `wp:navigation` block by `ref` so menus stay
editable in Appearance → Editor.

The theme's hamburger ships without an accessible name. Add `aria-label`, `aria-controls`
and `aria-expanded`, plus a small delegated script that flips `aria-expanded` and the label
when it toggles. `examples/generate_chrome.py` shows the exact patches.

**Footer: rewrite freely** with GreenLight elements on `gt-footer-grid`. Wrap link columns in
`<nav aria-label="…">`.

## Interactivity

GreenLight reads frontend scripts from the `gspb_block_js` option, not from post content.
The editor writes that option on save, so a block inserted over REST carries `customJs`
that never runs. Upstream gives three ways to deal with it, in preference order:

| | How | Cost |
|---|---|---|
| A | WP-CLI `wp option update gspb_block_js` | needs shell access to the host |
| B | `POST greenshift/v1/update-custom-js`, `WP.set_block_js()` | needs `manage_options` |
| C | put the script in a `wp:html` block at the end of the page | none |

**This skill uses C by default**, which is a documented fallback rather than a workaround:
it needs no extra capability and survives hosts that block the endpoint. Strip `customJs`
and `customJsEnabled` from the block when you do, or the script is defined twice. On this
path you **must** replace `{{PLUGIN_URL}}` with the real plugin path, because raw `wp:html`
output is never processed by PHP. Options A and B keep the placeholder, which PHP resolves
at render time.

Whichever route, use **event delegation on `document`** so behaviour survives re-saves and
reordering, and test on the front end: the editor canvas never runs these scripts.

To show/hide, set `el.style.display`. **Never use the `hidden` attribute**: block CSS with
`display:flex` beats `[hidden]`, so elements report themselves hidden while staying visible.
Verify with `offsetParent === null` or computed display, not with the property you just set.

Filter pattern that works: `button` chips with `aria-pressed`, a container with `role=group`
and a label, an `aria-live` region announcing the result count, and an empty-state message.
Card categories go in `data-*` attributes declared in the block JSON.

Client-side filtering suits a curated set. Only reach for posts + categories with a
GreenLight query grid when the client needs to add items themselves, and WooCommerce only
when they actually sell online. A custom post type is rarely the right first step.

## Animation

Upstream's pointers are in `instructions/scripts.md` and `validate-scripts.md`: scripts
ride on a block as `customJs`, the front end reads them from the `gspb_block_js` option
(so REST-inserted scripts need option B or C above), and **never hide an element with
CSS and reveal it with a script**, because the editor canvas runs no scripts and the
element would vanish there. Set the hidden start state inside the script, right before
animating. Prefer CSS transitions for hover and small entrances; reach for a library for
scroll-driven and sequenced motion.

Two things upstream gets wrong for this theme, both verified on gl-page-builder 3.3.7:

- The plugin folder is `gl-page-builder`, not `greenshift-animation-and-page-builder-blocks`.
  Read it with `WP.greenshift_plugin_url()`; a guessed path 404s silently.
- `import gsap from '{{PLUGIN_URL}}/libs/motion/gsap.js'` fails twice: that file does not
  exist, and the bundled GSAP is a classic UMD build that throws when imported as a module.

What the plugin ships, relative to its folder: `libs/gsap/gsap.min.js` (GSAP 3.12.2, global
`gsap`) with `ScrollTrigger`, `ScrollToPlugin`, `Flip`, `SplitText`, `TextPlugin` and
`Observer` beside it, and Motion 12 as an ES module at `libs/motion/motion.js`. Nothing
else to load from a CDN; the client already pays for these.

```python
url = wp.greenshift_plugin_url()
page += blocks.gsap_script("""
  gsap.utils.toArray('.ketup-card').forEach(card => {
    gsap.set(card, {opacity: 0, y: 24});
    gsap.to(card, {opacity: 1, y: 0, duration: 0.6, ease: 'power2.out',
                   scrollTrigger: {trigger: card, start: 'top 85%'}});
  });
""", url)                                            # classic tags + registerPlugin, last in the page
page += blocks.motion_script("""
  inView('.ketup-stat', ({target}) => animate(target, {opacity: [0, 1], y: [16, 0]}, {duration: 0.5}));
""", url)                                            # ES module import
```

Both helpers wrap the body in a `prefers-reduced-motion` guard, so users who asked for
less motion get the resting state immediately. Keep that: it is also what the stylebook's
reduced-motion rule promises for CSS.

GreenLight blocks also carry a native `animation` attribute (the theme's mobile panel
uses `{"type":"clip-down","duration":800,"onclass_active":true}`); it is undocumented
upstream, so copy a working shape from the theme rather than inventing one.

Verification is by the front end in a real browser. The in-app browser pane never advances
animation frames, so tweens sit at their first frame there; `ScrollTrigger` callbacks and
console errors are observable, tween progress is not. `reference/site-conventions.md`
lists the other things headless rendering never does.

## Interactive components

`blocks.py` builds four components as semantic, accessible markup rather than the plugin's
native `isVariation` types. The native accordion/tabs/counter/countdown load their
front-end scripts from the same option the editor writes on save, so a native-variation
block pushed over REST renders inert; these carry their behaviour in one page script
instead, and the accordion needs no script at all.

| Helper | Markup | Script |
|---|---|---|
| `accordion(seed, items, exclusive=True, open_first=False)` | native `<details>/<summary>` | none; `exclusive` uses the HTML `name` attribute for single-open (Chrome 120+/Safari 17.4+/FF130+, older browsers allow several open) |
| `tabs(seed, panels)` | `role=tablist` buttons + `role=tabpanel` regions | `component_scripts()` |
| `counter(seed, value, suffix='')` | a `<span>` whose text is the final value | `component_scripts()` (counts up on first view, respects reduced motion) |
| `countdown(seed, deadline_iso)` | four labelled cells | `component_scripts()` |

Emit `blocks.component_scripts()` once, last in the page content. It is event-delegated and
idempotent. Tabs and counter render fully visible so the block is editable and degrades to
readable content with scripts off; the script sets the hidden/zero state, never base CSS.
The stylebook ships `gt-acc-*`, `gt-tab*`, `gt-cd-*` classes for all four.

**`wp:html` scripts must not contain `&`.** WordPress entity-encodes it to `&#038;` and a
`<script>` never decodes entities, so `a && b` reaches the engine broken and throws at parse
time. Write `&&` as nested `if`s or `!(!a || !b)` (`||` is unaffected), or store the script
with `WP.set_block_js()`, whose option path is not encoded. `script_block()` refuses a
literal `&` rather than shipping it broken.

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

`python scripts/launch.py plugins` installs FluentSMTP and Rank Math from wordpress.org
and reports the state of Gravity Forms. Large plugins often return HTTP 500 on install
while the files land fine, re-read `GET /wp/v2/plugins` and activate what is present
rather than trusting the response.

**Forms are Gravity Forms, over its REST API v2** (`gf/v2`). It is licensed and not on
wordpress.org, so three steps stay manual, once per site: upload the zip, enter the
licence, and switch on Forms → Settings → REST API. Application passwords authenticate
and the user's Gravity Forms capabilities apply, so build as an administrator.
`python scripts/launch.py check` proves the path (create, read, update, delete a probe
form, no email sent) before you build on it.

`python scripts/launch.py form "<Business>"` creates the form in one `POST /gf/v2/forms`:
fields with integer ids, a default confirmation, an admin notification. Each field's
`adminLabel` carries its machine name (`name`, `email`, `message`) so later steps find
ids without guessing. Embed with `blocks.gravity_form(id)`, a real `wp:gravityforms/form`
block the client can reconfigure, inside a container carrying `gt-form-card`; the
shortcode `[gravityform id="N" title="false" description="false" ajax="true"]` is the
fallback for raw HTML.

**The form is one object.** Notifications and confirmations live on it, keyed by a
13-character id, and `PUT /gf/v2/forms/{id}` replaces the whole thing. Read, edit the two
dicts, write back; never POST a second form to change one. `launch.py` derives those ids
from the names, so a re-run updates in place instead of adding duplicates. Merge tags bind
by field id, `{Name:1}` not by label; `{admin_email}` and `{all_fields}` are built in. A
notification to the submitter is `toType:"field"` with `to` set to the email field's id.

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
2. `python scripts/check_blocks.py output/*.html` — audits generated markup **before** it
   is pushed: undeclared attributes, raw `id` instead of `anchor`, missing `type`,
   id/localId mismatch, CSSRender against the target. None of this is visible on a
   rendered page, which is why it has shipped broken more than once.
3. `python scripts/check_links.py`, internal links, in-page anchors, links to drafts, and
   whether the main nav is identical across pages. `verify.py` reads one page at a time and
   never follows a link, so every cross-page link defect survives it.
4. `python scripts/stylebook.py verify`, tokens and classes actually reach the browser, and
   no aliased token points at a preset the page never defines.
5. `python scripts/probe_responsive.py --parity` on a plugin version you have not built on
   before: responsive arrays, stylemanager classes and `compile_css()` parity, against the
   live renderer. Every rule in this file that starts "verified" was verified by it.
6. Browser at 375px, grids collapse, footer stacks, no horizontal overflow
   (`document.documentElement.scrollWidth <= innerWidth`).
7. Front-end click-through of anything interactive.

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
3. Contrast gate the palette → push the stylebook (`--theme` registers the tokens as theme
   presets and aliases the stylebook onto them)
4. Images: export → `prep_images.py build` (WebP) → `upload`, logo + alt text
5. Generate and push pages as drafts
6. Header: discover with `area='header'`, patch surgically if it carries GreenLight
   blocks, otherwise rewrite; footer rewrite
7. `check_blocks.py` on the output, then push; `verify.py --all` and
   `check_links.py` on the live pages, then the browser at 375px
8. Launch stack: plugins, form, emails, SEO, llms.txt
9. Work `reference/launch-checklist.md` and hand over the manual steps
