# Upstream block specification

The Greenshift element block format is defined by **GreenLight Vibe**, WPsoul's own Claude
plugin: <https://github.com/wpsoul/greenlight-vibe> (MIT). This file records the parts of
that specification this skill depends on, so nothing here rests on inference.

Each section names the upstream document it comes from. Where this skill's behaviour differs
from the spec, the difference is stated with the evidence for it rather than quietly
resolved, those are the places to re-check when either side changes.

Upstream also ships `scripts/convert.js` and `scripts/deconvert.js`, dependency-free Node
converters that turn a plain HTML file into block code and back. If you have an HTML design
in hand, that round trip is a legitimate alternative to generating blocks in Python, and the
deconverter is genuinely useful for editing a page that already exists.

---

## Block skeleton, `instructions/core-structure.md`

```html
<!-- wp:greenshift-blocks/element {JSON Parameters} -->
<html_tag class="optional classes" ...other_attributes>
  <!-- inner content -->
</html_tag>
<!-- /wp:greenshift-blocks/element -->
```

`tag` defaults to `div` when omitted. Prefer `tag:"a"` over `tag:"button"` for
button-like elements unless a form genuinely needs a `<button>`.

## `type`, how content is handled

| Value | Use |
|---|---|
| `"text"` | text only; the text is duplicated into `textContent`. Only `<strong>` and `<em>` allowed inside |
| `"inner"` | contains other blocks. A block holding both loose text and child blocks uses `inner` and wraps the loose text in its own `<span>` block |
| `"no"` | empty element, spacers, decorative shapes defined purely by style |
| `"html"` | whole-page fallback: HTML in `textContent`, CSS in `styleAttributes.customCSS_Extra`, JS in `customJs`, all JSON-escaped |

**This skill now always emits `type`, matching upstream.** `blocks.py` sets `inner` for
containers, `text` for text blocks, and `no` for empty elements, images and SVG icons.

This was not cosmetic. `convert.js` ends its block assembly with a literal
`// Always set type explicitly` followed by `params.type = effectiveType;`, and
`deconvert.js` reads `const type = attrs.type || 'inner'`. A text block with no `type`
therefore deconverts as a container and loses its `textContent`. Images are the
non-obvious case: `getTypeFromTag` returns `'image'` for `img`, but the img branch
overrides it with `effectiveType = 'no'`, so `type:"no"` is what actually ships.
The emitted set is `text`, `inner`, `no`, `html` (`html` for `<br>`/`<hr>`);
`deconvert.js` also recognises `unicorn`.

## Responsive arrays, `instructions/core-structure.md`

`styleAttributes` values are arrays across **four** breakpoints:

```
["desktop", "tablet", "mobile_landscape", "mobile_portrait"]
```

Fewer values apply upward: `["10px"]` covers all four, `["20px","15px"]` means desktop 20px
and everything below 15px. Upstream is explicit that a desktop-only value is written
`["10px"]` and **not** `["10px", null, null, null]`.

**This skill uses single-value arrays throughout and keeps every breakpoint in a stylebook
class.** That is a deliberate narrowing, not ignorance of the format: multi-value arrays
pushed over REST were observed dropping their smallest entry so mobile inherited desktop.
The single-value rule sidesteps it and keeps media queries in one place. If you do use
multi-value arrays, verify the smallest breakpoint on a real device.

## Attributes, `instructions/attributes.md`

`className` must be duplicated in the HTML `class` attribute. `anchor` sets the HTML `id`. There is no raw `id` parameter, and passing one fails validation.

Links: `href`, `linkNewWindow` (emits `target="_blank"` **and** `rel="noopener"`
automatically), `linkNoFollow`, `linkSponsored`, `title`.

Images: `src`, `alt`, `originalWidth`, `originalHeight`, `fetchpriority:"high"` for the LCP
image. Always `loading="lazy"` in the HTML, and when `originalWidth`/`originalHeight` are in
the JSON the matching `width`/`height` attributes must be on the `<img>` too.

Media: `poster`, `loop`, `autoplay`, `muted`, `playsinline`, `controls`.
Tables: `colSpan`, `rowSpan`.

**Forms** use a `formAttributes` object, and `type` goes *inside* it, never in the main JSON:

```json
{"textContent":"Submit","tag":"button","type":"text","formAttributes":{"type":"submit"}}
```

**`dynamicAttributes`** carries anything without a dedicated parameter, `data-*`, `aria-*`,
`role`, as `[{"name":…,"value":…}]`, and must also appear in the HTML.

## Icons, `instructions/attributes.md`

`tag:"svg"` with an `icon` object:

```json
{"tag":"svg","icon":{"icon":{"svg":"…","image":""},
 "fill":"currentColor","fillhover":"currentColor","type":"svg"}}
```

SVG markup inside `icon.icon.svg` **must** be unicode-escaped: `<` → `<`, `>` →
`>`, `"` → `"`. Strip `xmlns` from `<svg>` and `<path>` in the emitted HTML.

## CSS delivery. Upstream `SKILL.md`, "Agentic Export to WordPress"

Upstream distinguishes two targets:

- **pages and posts**, collect the CSS into one string and write it to the `_gspb_post_css`
  post meta field
- **patterns and templates**, put `"CSSRender": "1"` on the blocks instead

**This skill takes a third path and it matters.** It sets `"CSSRender": true` (boolean) on
every block carrying `styleAttributes` and *clears* `_gspb_post_css` after each update, so
the server compiles CSS from the block attributes and no stale meta can survive a
regeneration. Verified working across a full production site: pages render styled, and
regenerated pages never inherit CSS from a previous version.

The trade-off is real. The upstream `_gspb_post_css` route means one stylesheet per page
instead of per-block compilation, which is likely cheaper at render time. If a page renders
unstyled, check which of the two mechanisms is actually in play before changing anything, mixing them is what produces "old styles keep coming back".

## Custom JavaScript, `instructions/scripts.md`

Blocks carry `customJs` (string) plus `customJsEnabled: true`. Values can be injected with
`customJsControllers: [{"name":…,"value":…}]` referenced as `{{NAME}}` in the code.
`{{PLUGIN_URL}}` resolves to the plugin directory. Scripts are served from the
`gspb_block_js` option rather than from post content.

Scoping is by the block's own `localId` class. Scripts **do not run in the block editor**.

Upstream's rule, which this skill states as its own: never make visibility depend on a
script. No base `opacity:0`, `display:none` or `visibility:hidden` waiting for JS to undo, set the hidden state inside the script immediately before animating, so the content is
visible in the editor and in any renderer where the script never fires.

For agentic export upstream says to move scripts out of `customJs` and into `wp:html` blocks
at the end of the page, which is what this skill does.

## Global settings, `instructions/global-settings.md`

Documented endpoint: `/wp-json/greenshift/v1/figma_settings`, basic auth with an application
password. **Verified on a live install: `figma_settings` and `global_settings` return byte
identical payloads. They are aliases.** This skill calls `global_settings`; either works.

Writes shallow-merge top-level keys only, and **sending a `variables` array replaces the
whole list**, so always read, merge locally, then write. This skill's `stylebook.py` and
`WP.gs_merge()` do exactly that.

Variable shape (confirmed against a live install):

```json
{"variable": "--gt-cream", "variable_value": "#f7ecd9", "label": "cream",
 "value": "var(--gt-cream)", "group": "imported"}
```

`figma_fonts` accepts `{"fontFamily","fontStyle","fontFile"}` entries; the plugin downloads
the files server-side into `/uploads/GreenShift/`. This skill does not automate fonts.

## Design tokens, `instructions/variables.md`

Upstream prefers the theme's own WordPress preset variables over invented ones:

- font size `var(--wp--preset--font-size--*)`, from `mini` up to `god`
- line height `var(--wp--custom--line-height--*)`
- spacing `var(--wp--preset--spacing--20 … --110)`
- radius `var(--wp--custom--border-radius--*)`, shadows `var(--wp--preset--shadow--*)`
- sizes `var(--wp--custom--size--*)`
- **content width `var(--wp--style--global--content-size, 1290px)`**, prefer this over
  wide-size, and over the hardcoded 1290px this skill's `container()` defaults to

`--` must be escaped to `--` inside block-comment JSON.

**This skill defines its own `gt-` token set.** That is defensible for an agency build with
its own design system, and it costs theme compatibility: a token named against the WordPress
preset scale keeps working if the theme is restyled or replaced. Prefer the preset variable
wherever one already expresses the value.

## Source HTML conventions. Upstream `SKILL.md`, step 1

Relevant when authoring HTML for `convert.js`: vanilla HTML only (no React, TypeScript or
Tailwind), unique class prefixes of at least four letters, no `:root` variables (put them on
a parent block class), no styling on `body` or `*`, CSS inside
`<style data-wp-block-html="css">`, JS inside `<script data-wp-block-html="js">`, and
entrance effects done with `@keyframes` rather than JavaScript.

---

## Verified on a live install

A draft page pushed through this skill's emitter and read back over REST (18 blocks,
Greenshift active):

- every block carries `type`, 7 `inner`, 9 `text`, 2 `no`, and it survives the save
- all 9 blocks with `styleAttributes` carry `CSSRender: true`
- `id` equals `localId` on every block
- every `styleAttributes` value is a single-element array
- `--` dash escapes and the `<` icon escapes both round-trip intact
- no texturisation of the block JSON
- rendered output: 1 h2, 3 h3, 3 article, 1 svg, 1 a, all text content present

WordPress re-serialises the JSON minified on save, so verification must parse rather than
grep. See the troubleshooting entry on that.
