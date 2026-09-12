# FSE layout and native GreenShift blocks

Read this before emitting any section. The GreenLight theme is a block theme
(`theme.json` v3). Full Site Editing already owns width. GreenShift's inspector
already owns background, spacing, flex and typography. Custom CSS that repeats
either is dead weight a developer cannot usefully edit.

## What the theme already does

Verified against GreenLight 2.1 (`theme.json`, `templates/no-title.html`,
`templates/page.html`, `assets/style.css`):

| Token / setting | Value | Effect |
|---|---|---|
| `settings.layout.contentSize` | `748px` | Constrained post content |
| `settings.layout.wideSize` | `1200px` | `--wp--style--global--wide-size` |
| `useRootPaddingAwareAlignments` | `true` | `alignfull` goes edge to edge |
| Root padding | `1.25rem` left/right, `0` top/bottom | Side inset for non-full blocks |
| `--wp--custom--spacing--side` | `min(3vw, 20px)` | Section side pad |
| `blockGap` | `1.6rem` | Flow margin between siblings |
| Page template for landing pages | `no-title` | Header + `post-content` constrained + footer. No extra H1 |

Landing pages use the `no-title` template. `post-content` is `layout.constrained`.
A child without `alignfull` / `alignwide` is capped at `contentSize`. A child with
`align":"full"` and class `alignfull` is already 100% of the viewport. Setting
`width`, `max-width`, `min-width` or `100vw` on that section does nothing useful
and fights the inspector.

`.wp-section` / `.wp-content-wrap` are **not** in the theme stylesheet. Width
comes from FSE alignment, not from copying upstream's sample `.wp-section{…}` CSS
into the page. Do not paste that CSS into a stylemanager or `customCSS_Extra`.

## Canonical section (what the editor shows)

One GreenShift Element variation pair. This is what inserting **Section** in the
plugin produces (`isVariation` from `block-manager-page.php` / `convert.js`):

```
section  isVariation: contentwrapper   align: full   tag: section
  └─ div   isVariation: nocolumncontent   data-type: content-area-component
       └─ the actual content (stack, columns, cards)
```

`scripts/blocks.py` `section()` + `container()` emit this.

**On the section (inspector Layout + Spacing + Background), set only:**

- `align":"full"` and class `alignfull` (required for FSE full bleed)
- `display` / `flexDirection` / `justifyContent` / `alignItems` / `rowGap`
  (heroes: column + center + a gap; left-aligned bands: `flex-start`)
- `paddingTop` / `paddingBottom` (the band's rhythm)
- `paddingLeft` / `paddingRight` using
  `var(--wp--custom--spacing--side, min(3vw, 20px))` (or `--wp--spacing--side`)
- `marginTop` / `marginBottom` `0px` so core flow margin does not seam bands
- `position: relative` only if a background video or overlay child needs it
- `backgroundColor` and/or `backgroundImage` (see below)

**Never on the section:** `width`, `maxWidth`, `minWidth`, `100%`, `100vw`,
`calc(100% - …)`. FSE already stretched it.

**On the inner content area only:**

```
maxWidth: ["100%"]
width: ["var(--wp--style--global--wide-size, 1200px)"]
isVariation: nocolumncontent
```

That is the measure. Do not also `alignItems: center` here unless the design is
a centered stack; left-aligned heroes stay `stretch` / `flex-start`.

## Two-plus columns

Do not invent a CSS grid on the section. Use the plugin's column section:

```
section  isVariation: contentcolumns   align full
  └─ div  isVariation: contentarea
        flexDirection row, flexWrap wrap
        flexColumns_Extra: N
        flexWidths_Extra: {
          desktop: {name: "50/50", widths: [50, 50]},
          tablet:  {name: "50/50", widths: [50, 50]},
          mobile:  {name: "100/100", widths: [100, 100]}
        }
        columnGap / rowGap
        width: wide-size, maxWidth 100%
     ├─ column inner
     └─ column inner
```

`blocks.columns()` emits this. Collapse to one column on mobile via
`flexWidths_Extra`, not a media query in `customCSS_Extra`.

## Backgrounds: inspector, not extra blocks

A full-bleed photo or colour in the design is the **section's background**.
A developer must be able to change it from the block Background panel.

| Design | Put it here | Do not |
|---|---|---|
| Solid fill | `backgroundColor` (prefer `var(--wp--preset--color--…)` ) | A coloured empty `div` |
| Photo / texture | `backgroundImage: ["url(…)"]`, `backgroundSize: ["cover"]`, `backgroundPosition: ["center"]` | An `<img>` stretched behind the copy |
| Gradient | `backgroundImage: ["linear-gradient(…)"]` plus `imageGradient_Extra: true` | Extra CSS |
| Photo + dim overlay | One `backgroundImage` with `linear-gradient(rgba(0,0,0,.45), rgba(0,0,0,.45)), url(…)` and `imageGradient_Extra: true` | A second overlay `div` plus custom CSS |
| Decorative inline image (product, portrait, icon) | `image()` / `tag: img` as **content** | Background |

`isVariation: "cover"` is the plugin's cover-with-image variation. Use it when
the block *is* a cover. Do not fake a cover with a positioned `<img>` sibling.

## Videos: background vs player

| Design | Block |
|---|---|
| Ambient hero video (no controls) | Self-hosted: `background_video()` as first child of a `position:relative` section, `objectFit: cover`, `pointerEvents: none`, autoplay/muted/loop/playsinline. YouTube/Vimeo: `isVariation: youtubeplay` / `vimeoplay` (plugin docs: these exist *for* backgrounds). |
| User-controlled player | `tag: video` with `controls: true`, or the lightbox variation. |
| Thumbnail + play | `isVariation: videolightbox` |

Do not drop a full-size `<video>` or `<img>` into the flow and then `position:absolute`
it with a page stylesheet. The parent section owns the clip (`overflow: hidden`).

## Editor-first style rule

Emit properties that GreenShift's element inspector already edits
(`styleAttributes` camelCase arrays). That is how a developer restyles the page.

Allowed on a block:

- Spacing, size of **content** (not of full-bleed sections), typography, colour
- Flex / grid that the Layout panel shows (`display`, `gap`, `flexDirection`,
  `flexColumns_Extra`, `flexWidths_Extra`)
- Background properties above
- `_hover` / `_focus` suffixes
- Theme tokens: `--wp--preset--*` and `--wp--custom--*`

Forbidden unless there is no inspector equivalent:

- `customCSS_Extra`, `customCss`, a stylemanager class that only sets
  `width:100%`, `display:flex`, or copies `.wp-section`
- `core/html` for page content
- Absolute pixel canvases (`width:1440px` on a section because the Penpot
  board was 1440)
- Tailwind / React / `:root` / `body` / `*` in page CSS

Shared repeating patterns (cards, buttons, grids used on every page) still
belong in the **stylebook**, because the inspector cannot keep ten copies in
sync. One-off section chrome belongs on that section's `styleAttributes`.

## Element variations the converter already maps

From `gl-page-builder` block manager + `convert.js`:

| `isVariation` | Use |
|---|---|
| `contentwrapper` | Full-bleed section, no columns |
| `nocolumncontent` | Inner wide-size wrap |
| `contentcolumns` + `contentarea` | Section with columns |
| `cover` | Cover with image |
| `button` / `buttoncomponent` | Buttons (`gs_button` + theme button tokens) |
| `img` / `video` / `h1`–`h3` / `p` / `a` | Matching tags |
| `accordion` `tabs` `counter` `countdown` `marquee` | Interactive presets |
| `youtubeplay` `vimeoplay` `videolightbox` | Video |
| `stylemanager` | Page-local classes that *cannot* be inspector fields |
| `querygrid` (own block) | Archives / loops only when asked |

Prefer these over a generic `div` plus a private class.

## GreenLight `theme.json` palettes to consume

`brand`, `text-on-brand`, `textcolor`, `heading`, `border`, `background`,
`base`, `contrast`, `lightgrey`, `card-base`, `card-border`, `card-text`.
Font sizes: `mini` `xs` `s` `r` `m` `l` `xl` `xxl` `high` `grand` `giga`
`giant` `colossal` `god`. Spacing presets `20`–`110`. Shadows: `accent`
`mild` `soft` `elegant` `focus` `highlight`.

Do not invent a parallel colour named `hero-green` when `brand` is the same hex.

## FSE chrome

Header and footer are template parts (`parts/header.html`, `parts/footer.html`),
not page blocks. Patch a GreenLight header; rewrite the footer. Pages that are
true landing pages use `template: no-title`. Do not re-emit the site header
inside post content.
