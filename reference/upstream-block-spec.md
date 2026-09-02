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

**Single-value `styleAttributes`.** The format is a four-value responsive array
(`["desktop","tablet","mobile_landscape","mobile_portrait"]`, fewer values applying upward).
This skill emits one value and keeps breakpoints in stylebook classes, because multi-value
arrays pushed over REST were observed dropping their smallest entry so mobile inherited
desktop. Narrowing also makes `compile_css()` tractable.

**A `gt-` token set alongside the theme's.** Upstream prefers the theme's own
`--wp--preset--*` and `--wp--custom--*` variables. Consume those where they exist; a
parallel system drifts.

**No `dynamicGClasses` / `stylemanager`.** This skill carries shared CSS in the Greenshift
stylebook (`global_settings`) or, on the core backend, the FSE global-styles record.
Upstream's converter puts local classes in a stylemanager block instead. Not yet reconciled,
and the most likely source of the next surprise.

**Not using `convert.js`.** Upstream's documented workflow is to author clean vanilla
HTML/CSS/JS and run their converter. This skill hand-emits blocks from Python, which suits
generating many pages from structured data but means every format rule has to be
reimplemented correctly here. When you have a single HTML design in hand, their converter
is the better tool and the round trip through `deconvert.js` is genuinely useful.

---

## Verified against a live install


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
