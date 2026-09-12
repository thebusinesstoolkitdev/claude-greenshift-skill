# Design sources → GreenShift blocks

Extract structure first, then tokens, then media. Never rebuild a section from
one giant PNG. Get the **section map** approved before generating.

The write path never changes: tokens → stylebook, images → media library,
vanilla structure → `section()` / `container()` / `columns()` / `block()`,
then `WP.push_page()`. Penpot, Paper, Pencil, Figma and screenshots only fill
the intermediate.

Always rewrite the dump to **vanilla HTML** (prefixed classes, no Tailwind, no
React) *or* skip HTML and call `blocks.py` directly from the section map. Direct
`blocks.py` is preferred: `convert.js` will happily copy `width: 1440px` off a
board into a section.

## Shared extraction checklist

1. Name every top-level band (hero, logos, features, proof, CTA, footer).
2. For each band record: background (colour / image / video / none), alignment
   (center vs start), inner layout (stack / 2-col / 3-col / grid), gap, pad.
3. Classify every image: **section background**, **content image**, or **icon**.
4. Pull actual copy. Do not invent lorem.
5. Map colours and type to `theme.json` presets / stylebook tokens.
6. Generate with `section()` + `container()` or `columns()`. Run
   `python scripts/check_blocks.py output/*.html --target page`.

## Penpot (MCP `user-penpot`)

Paper Desktop is not Penpot. Use the Penpot MCP against the open file.

1. `high_level_overview` once per session, then `penpot_api_info` if a type is
   unclear.
2. Walk the page board: top-level frames are sections. Ignore prototype
   overlays unless they are real UI.
3. Read fills, layout (flex/grid), gap, padding, typography from the node, not
   from a screenshot.
4. `export_shape` for **content** rasters and icons. A full-bleed fill is not an
   export of the whole section; it is `backgroundImage` on the section block.
5. Board width (1440, 1920) is **not** a CSS width. Drop it.

Penpot absolute groups: flatten to flex stacks that match the visual order.
Do not emit `position:absolute` for every frame.

## Paper / Pencil (Paper Desktop MCP)

Paper must be open. Never read `.pen` from disk.

1. `get_basic_info` — artboards are pages or breakpoints.
2. `get_tree_summary` — section map.
3. `get_computed_styles` + `get_node_info` — copy, type, colour, spacing.
4. `get_jsx` **inline-styles format**, never Tailwind. Rewrite to vanilla HTML
   or to `blocks.py` calls. Paper's "build a website" guide is React+Tailwind;
   GreenLight forbids both.
5. `export` / `get_fill_image` for content assets. A frame fill is a background.
6. `get_screenshot` for QA only.

Paper tokens → stylebook `variables` / `colours` / `global_classes` via
GET-merge-write. Do not send `figma_*` keys on stock 3.3.7.

## Figma

REST, no MCP. `GET /v1/files/{key}?depth=2`, `/nodes`, `/images?format=png&scale=2`.
Header `X-Figma-Token`. Same intermediate as Paper. Auto-layout frames become
flex; ignore absolute leftovers.

## Screenshots / sketches

Last resort. Infer the section map and confirm it. Export real assets from the
design file if one exists; do not slice the screenshot into "background.png"
plus "text.png".

## Translation table (design → blocks)

| You see in the file | You emit |
|---|---|
| Full-width coloured band | `section(bg=token)` , no width |
| Full-width photo behind copy | `section(bg_image=url)` |
| Full-width video behind copy | `section()` + `background_video()` or youtubeplay/vimeoplay |
| Centered headline + button | Inner stack: `flexDirection column`, `alignItems center`, `rowGap` |
| Left copy / right image | `columns(..., widths=[50,50])` |
| Card row | `columns` or `grid()` with stylebook class, not 4 absolutely placed frames |
| Logo / product shot | `image()` |
| Icon | `svg_icon()` or uploaded SVG `image()` |
| Pill / badge | `block` `div` with padding + radius + `backgroundColor` |
| Button | `button()` / `gs_button` tokens, not a styled `div` |
| Section 1440px wide | `alignfull` only |

After conversion, open the mental editor: if a developer cannot change the
background, the gap, or the column split from the GreenShift sidebar, the
markup is wrong. Rebuild that band.
