# Troubleshooting

Every entry here is a bug that actually shipped and cost time. Symptom first, because
that is what you will have when you arrive.

---

## Blocks render with no styling at all

**Symptom** — Page structure is right, content is right, everything is unstyled. Block
`gsbp-xxxxxxx` classes are in the HTML but no matching CSS rules anywhere.

**Cause** — Greenshift normally compiles block CSS *in the editor* on save. Blocks pushed
over the REST API never pass through the editor, so nothing compiles them.

**Fix** — Add `"CSSRender": true` to every block that carries `styleAttributes`. This tells
the server to compile the styles at render time. `gsblocks.block()` does this automatically.

**Check** — `python scripts/verify.py <url>` reports `blocks: N, with CSS: M`. If M is 0,
this is your problem.

---

## Mobile layout ignores the mobile breakpoint

**Symptom** — Tablet styling is correct, but at 375px the layout falls back to the desktop
value. A three-column footer stays three columns and squeezes.

**Cause** — Greenshift's *server-side* CSSRender mishandles three-entry responsive arrays.
`["1fr 1fr 1fr", "1fr 1fr", "1fr"]` compiles the tablet entry scoped to
`(min-width:768px) and (max-width:991.98px)` and drops the mobile entry entirely. The
editor's own compiler handles these fine — which is why it looks correct in the editor and
breaks on the front end.

**Fix** — Never put multi-value arrays in `styleAttributes` on REST-pushed blocks. Use a
single value with `clamp()`/`min()` for fluid properties, and put every breakpoint in a
stylebook global class (`gt-grid-4`, `gt-footer-grid`, …). Media queries inside global class
CSS are emitted verbatim and work correctly.

---

## "This block contains unexpected or invalid content" / Attempt recovery

**Symptom** — Opening the page in the editor offers "Attempt recovery". Accepting it strips
your `data-*` / `aria-*` attributes and interactive features stop working.

**Cause** — Gutenberg re-generates each block's HTML from its JSON and compares. Attributes
present only in the raw HTML do not survive the round trip, so validation fails.

**Fix** — Declare every custom attribute in the block JSON *and* render it in the HTML:

```json
"dynamicAttributes": [{"name": "data-cat", "value": "dresses"}]
```

`gsblocks.block(attrs={'data-cat': 'dresses'})` handles both sides for you.

---

## Filter/toggle JavaScript "works" but nothing visibly changes

**Symptom** — Clicking a filter updates `aria-pressed`, the console shows the handler
running, `el.hidden = true` is set — and every card stays on screen.

**Cause** — The UA rule `[hidden] { display: none }` has almost no specificity. Any block
CSS setting `display: flex` on that element wins, so the element stays visible while
*reporting* itself as hidden. Checking `el.hidden` in the console confirms a lie.

**Fix** — Set inline style instead: `el.style.display = 'none'` / `''`.

**Verify visually, not by property**: an element is genuinely hidden only if
`el.offsetParent === null` or `getComputedStyle(el).display === 'none'`. Assert on that.

---

## Custom scripts do nothing in the editor

Expected. The editor canvas never executes scripts inside `core/html` blocks. Test all
interactivity on the front end. Use event delegation bound to `document` so handlers survive
re-saves, block reordering, and late-loading markup.

---

## Element styles are overridden by the theme

**Symptom** — `h1` font-size from the stylebook is ignored; the theme's size wins.

**Cause** — Both rules have identical specificity, and the theme's stylesheet loads later.

**Fix** — Prefix element-style selectors with `body`: `body h1 { … }`. Keep the editor
counterpart as `.editor-styles-wrapper h1 { … }`.

---

## Page shows two `<h1>` elements

The theme prints the page title above your content. Assign the template that omits it:

```json
{"template": "no-title"}
```

Confirm the slug exists with `GET /wp-json/wp/v2/templates` — themes name it differently.

---

## Old styles keep coming back after a REST update

**Cause** — If a page was ever opened and saved in the editor, `_gspb_post_css` post meta
holds a snapshot of compiled CSS which is enqueued alongside the fresh server-rendered CSS.

**Fix** — Clear it after pushing content:

```
POST /wp-json/greenshift/v1/css_settings   {"id": <post_id>, "css": ""}
```

`WP.update_page()` does this automatically.

---

## Stylebook update wipes other settings

**Cause** — `POST /greenshift/v1/global_settings` merges only at the top level. Whatever
array you send for `variables` or `global_classes` **replaces** the stored one.

**Fix** — Always read current settings, merge locally, send the complete array.
`WP.gs_upsert_classes()` / `gs_upsert_variables()` / `scripts/stylebook.py push` do this.

---

## Fluent Forms: duplicate notifications, or settings changes that do not stick

**Cause** — `POST /fluentform/v1/settings/{form_id}` **inserts a new row** unless you pass
`meta_id`. A second `notifications` row means two emails; a second `formSettings` row means
the old confirmation may still win.

**Fix** — Read the setting first, pass the row's `id` back as `meta_id`:

```python
row = wp.ff_settings(form_id, 'formSettings')[0]
wp.ff_save_setting(form_id, 'formSettings', updated_value, meta_id=row['id'])
```

Delete an accidental duplicate with `DELETE /fluentform/v1/settings/{form_id}` and
`{"meta_id": <id>}`.

Also note `POST /fluentform/v1/forms` rejects payloads without one of its own template keys
("The selected template couldn't be found") — duplicate the bundled demo form instead, then
overwrite its fields.

---

## Plugin install returns HTTP 500 but the plugin is there

Large plugins exceed the request timeout while unzipping. The files land; the response
fails. A retry then reports `folder_exists`.

**Fix** — Treat 500/`folder_exists` as "probably installed": re-read `GET /wp/v2/plugins`
and activate whatever is present. `WP.install_plugin()` implements this.

---

## Rank Math meta cannot be set over REST

`rank_math_title` / `rank_math_description` are not registered for REST until the setup
wizard has run, and even then may not be exposed.

**Workaround** — Rank Math's default description template falls back to the post excerpt,
which *is* a first-class REST field. Write excerpts and the descriptions appear.

Two manual steps remain: run the setup wizard, then **Settings → Permalinks → Save** to
flush rewrite rules, otherwise `/sitemap_index.xml` 404s.

---

## Scripted requests start returning 403

**Symptom** — curl/urllib worked, then every request returns 403 while a browser loads the
site fine.

**Cause** — Security plugins (SiteGround Security, Wordfence, …) rate-limit or block
non-browser user agents after repeated hits.

**Fix** — Send a real browser `User-Agent` (`scripts/verify.py` does), space out requests,
and when in doubt verify in a browser instead. This affects only front-end page fetches;
authenticated REST calls keep working.

---

## Front-end shows stale content after a push

Managed hosts run a proxy cache (`X-Cache-Enabled: True`). Append a unique query string to
bypass it while testing, and purge from the host panel before asking anyone else to look.

---

## A tool reports a failure you cannot reproduce by hand

Seen for real: a regex in a checker contained a literal backspace byte (`0x08`) because a
`\b` escape was interpreted when the file was written through a shell heredoc. The pattern
silently never matched, and the checker reported false failures.

**Rule** — When a check disagrees with a manual inspection, suspect the checker. Print the
values it is actually comparing (`repr()`), and `od -c` the source line if a regex is
involved. Write files with the editor tools rather than shell heredocs when they contain
regex escapes.
