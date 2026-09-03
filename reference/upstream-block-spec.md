# Divergence register

The block format is specified by WPsoul in <https://github.com/wpsoul/greenlight-vibe>
(MIT). **That repository is the specification. This file is not.**

Fetch and read the real thing:

```
python scripts/upstream.py sync
python scripts/upstream.py show <term>
python scripts/upstream.py show -f validate-styles.md
python scripts/upstream.py check      # non-zero when upstream has moved
```

`reference/upstream-pin.json` records the commit and a hash per spec file, so `check` tells
you exactly which documents changed since this skill was last reconciled against them.

## Why this file was demoted

It used to paraphrase the spec, built from web-page summaries rather than the source. The
paraphrase was wrong in ways that only surfaced when a build broke:

| Claimed | Actual |
|---|---|
| `CSSRender` is boolean `true` | it is the string `"1"` |
| CSSRender on pages, `_gspb_post_css` cleared | the reverse: no CSSRender on pages, CSS goes into that meta |
| no mention of `dynamicGClasses` | it is a core mechanism, with an `isVariation:"stylemanager"` block |
| `instructions/dynamic-content.md` exists | it does not; `validate-styles.md`, `validate-scripts.md` and `dynamic-placeholders.md` do, and were never listed |

A boolean `CSSRender` satisfies the PHP renderer, so the error rendered correctly and
survived a full production build plus a live round-trip test. That is the shape of this
bug class: wrong, and invisible until something specific breaks.

## Current divergences, deliberate

**Hand-emitted blocks by default.** Upstream's documented workflow is to author clean
vanilla HTML/CSS/JS and run `convert.js`. This skill hand-emits blocks from Python for the
many-pages-from-data case, and every format rule is reimplemented here, checked by
`check_blocks.py` and `probe_responsive.py`. For a single HTML design
`scripts/convert_html.py` runs upstream's converter and adds the delivery contract on top.

**Class-less CSS on template targets.** The converter files it as `customCss` on the
stylemanager, which only the editor compiles. This skill routes it to the stylebook instead
(`style_manager()` refuses `custom_css` on a template target), because a template part is
site-wide anyway. On page targets both agree: it goes into `_gspb_post_css`.

**GSAP loading.** Upstream imports GSAP as an ES module from
`{{PLUGIN_URL}}/libs/motion/gsap.js`. On the Greenlight build (`gl-page-builder`) that path
does not exist and the bundled GSAP is a UMD file that throws when imported as a module.
This skill loads it with classic script tags from `libs/gsap/`, reads the plugin folder
from the site, and imports only Motion (`libs/motion/motion.js`) as a module.
`blocks.gsap_script()` and `blocks.motion_script()` carry the working recipe.

## Retired divergences

**A `gt-` token set alongside the theme's** (reconciled 2026-09-02). Tokens now carry a
`kind`, `stylebook.py push --theme` registers each as a theme.json preset of that kind on
the user global-styles record and aliases the `gt-` variable onto it, and `map --apply`
points a token at an existing theme preset where the values already match. The `gt-`
names remain as aliases so generators do not change; the theme owns the values.

**No `dynamicGClasses` / stylemanager** (reconciled 2026-09-02). `style_manager()` emits
the converter's class shape (`value`, `type:"local"`, `css`, `selectors`), `compile_css()`
folds it into the page CSS, `check_blocks.py` audits it, and the probe verifies what the
PHP renderer emits: `dynamicGClasses[].css` and `selectors[].css`, never `customCss` or
`customCSS_Extra`.

**Single-value `styleAttributes`** (retired 2026-09-02). This skill used to emit one value
per property and forbid responsive arrays, on the strength of one observation that the PHP
renderer dropped the smallest entry. Reproduced against Greenlight 2.1 / gl-page-builder
3.3.7 with `scripts/probe_responsive.py`: every shape compiles correctly, smallest entry
included, at `max-width` 991.98px / 767.98px / 575.98px. `compile_css()` now mirrors those
breakpoints for page targets, and the core backend raises on multi-value arrays rather than
silently taking the first. The probe is the record; run it against a new plugin version
before re-opening this.

## convert.js: a rule is filed under the first class in its selector

`parseCss()` does `selectorPart.match(/\.([a-zA-Z_-][a-zA-Z0-9_-]*)/)` and attaches the
rule to that class as a local class with a sub-selector. Pushed through the PHP renderer on
a template target (2026-09-02, Greenlight 2.1 / gl-page-builder 3.3.7):

| Selector | Result |
|---|---|
| `.card .title{...}` | kept, as `selectors[].css` on `card` |
| `.wrap > .item{...}` | kept |
| `.ghost .title{...}` (no element has `ghost`) | kept: the class rides in `dynamicGClasses` and renders anyway |
| `body.dark .title{...}` | **rewritten** to `.dark .title`: the compound before the first class is dropped |
| `nav a{...}`, `:root{--x:1}` | **lost on template targets**: filed as `customCss`, which PHP never emits |

An earlier version of this entry said the `body.dark` rule was dropped. It is not; it is
weakened, which in practice styles the same elements unless another `.dark` ancestor
exists. The rules that really disappear are the class-less ones, and only where nothing
compiles `customCss`, which is template parts, templates and patterns.

`scripts/convert_html.py` reports both lists on every run. On a page target `--raw-css`
ships the original stylesheet as `_gspb_post_css`, so every selector survives exactly as
authored; on a template target move the class-less rules into a stylebook class.

---

## Verified against a live install

`scripts/probe_responsive.py --parity` is the standing record; the bullets below are what
it and the one-off probes of 2026-09-02 established on Greenlight 2.1 / gl-page-builder
3.3.7 / WordPress with LiteSpeed:

- `styleAttributes` arrays of 1 to 4 entries, `null` or `""` gaps, and `gridTemplateColumns`
  all persist over REST and compile to `max-width` rules at 991.98 / 767.98 / 575.98px
- `compile_css()` matches the renderer rule for rule on every shape
- a stylemanager's `dynamicGClasses[].css` and `selectors[].css` render with `CSSRender:"1"`;
  `customCss` and `customCSS_Extra` do not
- user-level presets under `palette.custom`, `fontSizes.custom`, `spacingSizes.custom` and
  `settings.custom` all reach the page as CSS variables, with kebab-cased slugs
- `--` dash escapes and the `<` icon escapes both round-trip intact
- a stylemanager carrier `<div>` is not printed on the front end, so its class list
  cannot leak styles into the page
- a block carrying editor-written `inlineCssStyles` plus `CSSRender:"1"` is emitted once,
  not twice
- the Greenshift stylebook CSS prints before the theme's `global-styles-inline-css`; REST
  GETs on `figma_settings` and `global_settings` are page-cached after a write and need a
  unique query string to read the live record

WordPress re-serialises the JSON minified on save, so verification must parse rather than
grep. See the troubleshooting entry on that.
