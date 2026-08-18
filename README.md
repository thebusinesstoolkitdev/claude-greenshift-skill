# claude-greenshift-skill

A [Claude Code](https://claude.com/claude-code) skill for building complete WordPress sites
on the **Greenshift** block builder (and the **Greenlight** FSE theme) from a design —
Figma, Paper, or a screenshot — entirely over the REST API.

No clicking through the block editor. Design system, pages, header, footer, forms and SEO
are all pushed as data, so a build is scriptable, reviewable and repeatable.

A four-page site — design tokens, pages, header, footer, responsive layout, accessibility
pass — takes about an hour end to end.

## What it gives you

- **The pipeline** — read a design, export and optimise its images, push a token-based
  design system, generate blocks, create pages, patch the theme's header and footer.
- **The API behaviour that is not documented** — the Greenshift responsive-array bug, the
  `CSSRender` requirement, Gutenberg's attribute-validation trap, Fluent Forms' duplicate
  settings rows, Rank Math's REST gap. Each one cost hours to find; see
  [`reference/troubleshooting.md`](reference/troubleshooting.md).
- **Working tools** — a REST client, a block builder, a WCAG contrast gate, a stylebook
  installer, a live-page verifier, and launch automation.

## Install

```bash
git clone https://github.com/thebusinesstoolkitdev/claude-greenshift-skill.git \
  ~/.claude/skills/greenlight-builder
```

Claude Code picks it up automatically. Ask for a build in plain language — *"recreate this
Figma design on my WordPress site"* — or invoke it directly with `/greenlight-builder`.

Requirements: Python 3.8+ (standard library only, Pillow for image conversion), a WordPress
site with Greenshift active, and an administrator application password.

## Quick start

```bash
cat > .env <<'EOF'
WP_URL=https://your-site.com
WP_USER=you@example.com
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
EOF

python -c "from scripts.wp_api import WP; print(WP().check())"   # expect is_admin + greenshift True

python scripts/check_contrast.py --bg "#fbf6ec" --fg body:#8c8172 accent:#e27b4b
python scripts/stylebook.py push reference/starter-tokens.json
python scripts/verify.py --all
```

## Layout

```
SKILL.md                      the skill itself — pipeline, rules, gotchas
scripts/
  wp_api.py                   WordPress / Greenshift / Fluent Forms REST client
  gsblocks.py                 Greenshift block builder (enforces the three hard rules)
  stylebook.py                push and verify the design system
  check_contrast.py           WCAG gate — fix the token, not the usage
  verify.py                   live-page checks: headings, alt text, accessible names, CSS
  launch.py                   plugins, branded form, notification emails, SEO
reference/
  starter-tokens.json         a complete working design system to adapt
  troubleshooting.md          symptom-first list of every bug that shipped
  launch-checklist.md         ordered, with the manual steps called out
  llms-template.txt           llms.txt scaffold for AI assistants
examples/
  generate_pages.py           a real four-page build, client details swapped out
  generate_chrome.py          header surgical patch + footer rewrite
```

## Three rules it enforces

1. **`"CSSRender": true`** on every block with `styleAttributes`. REST-pushed blocks never
   pass through the editor, so nothing compiles their CSS — without this the page renders
   completely unstyled.
2. **Single-value `styleAttributes`.** Server-side rendering mishandles multi-value
   responsive arrays: the mobile entry is dropped and mobile inherits desktop. Fluid values
   use `clamp()`; breakpoints live in stylebook classes.
3. **Declare custom attributes in the block JSON.** `data-*`, `aria-*` and `role` must be in
   `dynamicAttributes` as well as the HTML, or Gutenberg's validator strips them on
   "Attempt recovery".

## Accessibility is part of the build

Contrast is gated at the token level before anything is built on the palette. Generated
markup carries focus styles, a `prefers-reduced-motion` rule, labelled landmarks, exposed
`aria-expanded` / `aria-pressed` state, and a continuous heading outline.
`scripts/verify.py` checks the mechanical half of that on live pages — including the
accessible-name audit that PageSpeed Insights reports under *Agent Accessibility*.

## Notes

- Greenshift is required. The Greenlight theme is optional — only the header/footer section
  is specific to it, and the same approach works on any FSE theme.
- `.env` is gitignored. Nothing here stores credentials.
- Rotate any application password that has been shared during a build.

## Licence

MIT — see [LICENSE](LICENSE).

Greenshift and Greenlight are products of [Wpsoul](https://wpsoul.com/). This is an
independent, unaffiliated project.
