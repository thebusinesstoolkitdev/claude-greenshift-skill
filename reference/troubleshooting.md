# Troubleshooting

Every entry here is a bug that actually shipped and cost time. Symptom first, because
that is what you will have when you arrive.

---


Entries marked _Greenshift backend only_ do not apply when `blocks.py` is set to the `core` backend, which has no per-block compiled CSS and so cannot fail in these ways.

## Blocks render with no styling at all

_Greenshift backend only._

**Symptom**. Page structure is right, content is right, everything is unstyled. Block
`gsbp-xxxxxxx` classes are in the HTML but no matching CSS rules anywhere.

**Cause**. Greenshift normally compiles block CSS *in the editor* on save. Blocks pushed
over the REST API never pass through the editor, so nothing compiles them.

**Fix**. Add `"CSSRender": true` to every block that carries `styleAttributes`. This tells
the server to compile the styles at render time. `blocks.block()` does this automatically.

**Check**, `python scripts/verify.py <url>` reports `blocks: N, with CSS: M`. If M is 0,
this is your problem.

---

## Mobile layout ignores the mobile breakpoint

_Greenshift backend only._

**Symptom**. Tablet styling is correct, but at 375px the layout falls back to the desktop
value. A three-column footer stays three columns and squeezes.

**What it is not**. An earlier version of this entry blamed the PHP renderer for dropping
the mobile entry of three-entry arrays. That does not reproduce: against Greenlight 2.1 /
gl-page-builder 3.3.7, `["1fr 1fr 1fr", "1fr 1fr", "1fr"]` compiles to a desktop rule plus
`max-width` rules at 991.98px and 767.98px, and the 767.98px rule also covers 375px. Run
`python scripts/probe_responsive.py` to confirm on the site in front of you.

**Causes that do reproduce**, in order of likelihood:

1. The page target. Pages get no `CSSRender`, so the array is only compiled if you called
   `compile_css()` and pushed the result with `WP.set_post_css()`. An old `compile_css()`
   only emitted the desktop entry; the current one emits every breakpoint.
2. A stale copy of the CSS in `_gspb_post_css` from a previous push, or LiteSpeed's page
   cache serving the previous render. Clear both (`WP.clear_post_css()`, purge cache).
3. The core backend, which has no per-block breakpoints. `_core_style` raises on a
   multi-value array; if a generator swallows that error the breakpoint never existed.

---

## A class has a mobile media query, the element ignores it

_Greenshift backend, converter output especially._

**Symptom**. `.site-footer{flex-direction:column}` with `@media(min-width:900px){…row}` in
a local class, yet the footer stays a row at 375px and squeezes into two columns.

**Cause**. The same block also carries `styleAttributes` (`display`, `flexDirection`,
`alignItems`) that the converter lifted off the element's inline style or that an editor
save wrote back. The compiled id rule `.gsbp-xxx{flex-direction:row}` has the same
specificity as the class rule and prints after it, so the class's media query never wins.

**Fix**. Layout belongs in one place. Drop the per-block `styleAttributes` and any
`inlineCssStyles` for properties the class already sets, or express the breakpoint in the
block's own responsive array. `verify.py` cannot see this; a viewport sweep with
`getComputedStyle(el).flexDirection` at each width does.

---

## Animation script runs in the editor preview but not on the site, or 404s

**Cause**. One of three: the script sits in `customJs` on a REST-inserted block and the
`gspb_block_js` option was never written; the `{{PLUGIN_URL}}` placeholder was left in a
`wp:html` block, which PHP never processes; or the GSAP path was taken from upstream
(`libs/motion/gsap.js`), which does not exist on the Greenlight build, whose folder is
`gl-page-builder`. Importing the bundled `gsap.min.js` as a module also throws
("Cannot set property window").

**Fix**. Put page scripts in a `wp:html` block at the end of the page
(`blocks.script_block()`), get the folder from `WP.greenshift_plugin_url()`, and load GSAP
with classic script tags (`blocks.gsap_script()`). Motion is the one library there that is
a real ES module (`blocks.motion_script()`).

---

## Pseudo-element rules in a local class do nothing

The renderer emits `dynamicGClasses[].css` verbatim, but a rule carrying `content:""`
arrived on the page as `content:none`. Whether the quotes are lost in the block JSON round
trip or the plugin sanitises `content`, the result is the same: build hit areas and
decorations without `::before`/`::after`. A transparent border with a negative margin and
`box-sizing:content-box` enlarges a tap target without moving what is inside it.

---

## CSS in a stylemanager block reaches the editor but not the front end

_Greenshift backend, template parts / templates / patterns._

**Symptom**. A tag-led rule (`nav a`, `:root{--x}`, `@keyframes`) or a `customCSS_Extra`
shows in the editor canvas and is absent from the rendered page, while the local classes in
the same block work.

**Cause**. The PHP renderer behind `CSSRender` emits `styleAttributes` properties,
`dynamicGClasses[].css` and `dynamicGClasses[].selectors[].css`, and nothing else.
`customCss` and `customCSS_Extra` are compiled by the editor's JavaScript only. Verified
with `probe_responsive.py`; `check_blocks.py` flags both on a template target.

**Fix**. Put class-less CSS for a template part in the stylebook (the part is site-wide
anyway), or wrap it in a local class string so it rides in `dynamicGClasses[].css`. On a
page target nothing is lost: `compile_css()` includes both.

---

## "This block contains unexpected or invalid content" / Attempt recovery

_Greenshift backend only._

**Symptom**. Opening the page in the editor offers "Attempt recovery". Accepting it strips
your `data-*` / `aria-*` attributes and interactive features stop working.

**Cause**. Gutenberg re-generates each block's HTML from its JSON and compares. Attributes
present only in the raw HTML do not survive the round trip, so validation fails.

**Fix**. Declare every custom attribute in the block JSON *and* render it in the HTML:

```json
"dynamicAttributes": [{"name": "data-cat", "value": "dresses"}]
```

`blocks.block(attrs={'data-cat': 'dresses'})` handles both sides for you.

---

## Filter/toggle JavaScript "works" but nothing visibly changes

**Symptom**. Clicking a filter updates `aria-pressed`, the console shows the handler
running, `el.hidden = true` is set, and every card stays on screen.

**Cause**. The UA rule `[hidden] { display: none }` has almost no specificity. Any block
CSS setting `display: flex` on that element wins, so the element stays visible while
*reporting* itself as hidden. Checking `el.hidden` in the console confirms a lie.

**Fix**. Set inline style instead: `el.style.display = 'none'` / `''`.

**Verify visually, not by property**: an element is genuinely hidden only if
`el.offsetParent === null` or `getComputedStyle(el).display === 'none'`. Assert on that.

---

## Custom scripts do nothing in the editor

Expected. The editor canvas never executes scripts inside `core/html` blocks. Test all
interactivity on the front end. Use event delegation bound to `document` so handlers survive
re-saves, block reordering, and late-loading markup.

---

## Client says "I can't edit this section" / a section ignores the stylebook

The section was built as raw markup inside a `core/html` block instead of element blocks.
Symptoms cluster: the block editor shows one opaque code box where a grid of cards should
be, changing a `gt-` layout class or a token moves everything on the page except that
section, and `verify.py` reports clean while the section has no heading order and unlabelled
images.

`raw_html()` raises on content-shaped markup for exactly this reason. If a section already
shipped this way, rebuild it: `grid()` wrapping one `block(seed, 'article')` per card, each
holding a `heading()` and a `block(seed, 'p')`. Keep `core/html` for scripts, JSON-LD,
stylesheets and shortcodes.

## Element styles are overridden by the theme

_Greenshift backend only._

**Symptom**, `h1` font-size from the stylebook is ignored; the theme's size wins.

**Cause**. Both rules have identical specificity, and the theme's stylesheet loads later.

**Fix**. Prefix element-style selectors with `body`: `body h1 { … }`. Keep the editor
counterpart as `.editor-styles-wrapper h1 { … }`.

The `body` element style itself is the exception: the theme's own rule is also `body { … }`,
so prefixing does not break the tie. Use `html body { … }` there.

---

## Page shows two `<h1>` elements

The theme prints the page title above your content. Assign the template that omits it:

```json
{"template": "no-title"}
```

Confirm the slug exists with `GET /wp-json/wp/v2/templates`, themes name it differently.

---

## A WebP conversion came out bigger than the original

**Symptom**, `prep_images.py build` reports an output larger than its source, usually on a
logo, a screenshot, a diagram or a flat illustration rather than a photograph.

**Cause**, lossy WebP is tuned for photographic gradients. Large flat areas with hard
edges are its worst case: it spends bytes trying to reproduce edges it cannot represent.
PNG compresses exactly that content almost perfectly, so lossy WebP loses badly.

**Fix**, already handled: `encode_webp()` in `wp_api.py` encodes both ways and keeps the
smaller, and the build prints which mode won. If something still grows after that, the
source is probably a screenshot that should be an SVG, or a PNG that is already optimal, `keep_format=True` on `upload_media()` is the deliberate exception.

---

## A PNG or JPEG reached the media library

**Symptom**, `verify.py --all` or `prep_images.py audit` reports images served as PNG or
JPEG. Usually a logo, a favicon source, or something a client emailed and someone uploaded
through wp-admin.

**Cause**, `upload_media()` converts raster to WebP, but wp-admin does not. Anything added
through the WordPress UI bypasses the pipeline entirely.

**Fix**, convert and re-point, do not just re-upload alongside:

```
python scripts/prep_images.py build          # writes assets/<name>.webp
python scripts/prep_images.py upload         # new attachment id
python scripts/prep_images.py audit          # confirm zero
```

Update the block markup (and `media-map.json`) to the new id and URL, then delete the old
attachment. Leaving both means the old one stays reachable and may still be referenced by a
srcset the theme generated.

**Note**, the WordPress site icon and the theme logo are the usual stragglers; both accept
WebP. GIF is deliberately left alone because converting drops the animation.

---

## A stylebook change reads back as a no-op, repeatedly

**Symptom** — you push a stylebook update, read the settings back, and the change is not
there. Push again, same result. The front end may already be correct.

**Cause** — LiteSpeed and similar host caches will serve cached responses for
**authenticated REST GETs**. Look for `x-litespeed-cache: hit` on the response. Your read-back
is stale, not your write.

**Fix** — trust the front end over the read-back, add a unique query string to the read, or
purge before verifying. Do not keep re-pushing: the writes are landing, and repeated
"fixes" for a phantom failure are how real state gets damaged.

---

## A check says an attribute is missing, but the page is fine

**Symptom**, a script greps stored block content for `"CSSRender": true` or
`"type": "text"` and finds nothing, while the page renders correctly and the editor is
happy.

**Cause**. WordPress re-serialises block-comment JSON when it saves. What you pushed as
`{"id": "gsbp-abc1234", "CSSRender": true}` comes back as
`{"id":"gsbp-abc1234","CSSRender":true}`. The data is identical; the spacing is not.

**Fix**, parse the JSON, never grep it:

```python
payloads = [json.loads(x.replace('\u002d\u002d', '--'))
            for x in re.findall(r'element (\{.*?\}) -->', raw, re.S)]
missing = [d for d in payloads if 'styleAttributes' in d and d.get('CSSRender') is not True]
```

Escapes survive the round trip intact, so `--` has to be restored before the
JSON will parse. Verified on a live install: `type`, `CSSRender`, `localId` and the
unicode-escaped icon markup all come back byte-faithful apart from whitespace.

---

## A live page went back to draft after a content push

**Symptom**, a published page is suddenly a draft, or a draft is suddenly live, after a
routine content update.

**Cause**, the push helper sends `status` on every call. Written while every page was a
draft, it silently unpublishes the site the first time it runs against production. The
reverse also happens: a REST write can flip a draft to published as a side effect, with no
warning.

**Fix**, send `status` only when creating a page or deliberately changing state. Content
updates send `{"content": …}` and nothing else. Read the statuses back after any bulk push:

```python
for p in wp.get('wp/v2/pages?per_page=100&status=any&context=edit'):
    print(p['id'], p['status'], p['slug'])
```

---

## A section reads as unstyled, but only when it is full-width

**Symptom**, the same prose class looks right in a two-column layout and wrong in a
single-column section. Tokens are defined, CSS is compiled, nothing is missing.

**Cause**, the class has colour, size and line-height but no `max-width`, so full-width
prose runs to about 180 characters per line. The eye reads it as broken styling.

**Fix**, cap every prose class at 65-75ch (`reference/starter-tokens.json` does), and add
`text-wrap: balance` to `h1` to `h3`. See `reference/site-conventions.md`.

---

## A deleted stylebook class is still on the site

**Symptom**. You removed a class from the local definition and pushed, and elements still
pick it up.

**Cause**, the push replaces the array it sends; it does not diff. A class you stopped
defining was simply not in the payload, so the stored copy survives untouched.

**Fix**, prune explicitly. Read the stored classes, keep everything outside your prefix,
drop the prefixed ones no longer defined, then write the merged array.

---

## Old styles keep coming back after a REST update

_Greenshift backend only._

**Cause**. If a page was ever opened and saved in the editor, `_gspb_post_css` post meta
holds a snapshot of compiled CSS which is enqueued alongside the fresh server-rendered CSS.

**Fix**. Clear it after pushing content:

```
POST /wp-json/greenshift/v1/css_settings   {"id": <post_id>, "css": ""}
```

`WP.update_page()` does this automatically.

---

## Page Builder → Stylebook shows "This block has encountered an error and cannot be previewed"

**Cause**. A global class stored without `originalBlock` (and `type`, `attributes`, `tag`,
`selectors`), which is what `stylebook.py push` wrote before 2026-09-02 and what a hand
POST of `{"value","label","css"}` still writes. The screen groups classes by `originalBlock`,
gets the string "undefined", and throws on `"undefined".split("/")[1].charAt(0)`. The front
end never reads those keys, so the site looks fine while the screen is dead. A list-shaped
`elements` array (the screen expects an object keyed by tag) is the second candidate.

**Fix**. Re-run `python scripts/stylebook.py push <spec>`; it now normalises every stored
class to the screen's own shape and moves list-shaped element CSS into a class. Reload the
Stylebook tab.

---

## Stylebook update wipes other settings

**Cause**, `POST /greenshift/v1/global_settings` merges only at the top level. Whatever
array you send for `variables` or `global_classes` **replaces** the stored one.

**Fix**. Always read current settings, merge locally, send the complete array.
`WP.gs_upsert_classes()` / `gs_upsert_variables()` / `scripts/stylebook.py push` do this.

---

## Gravity Forms: 401 or 403 on every `gf/v2` call

**Cause**. The plugin is active (the `gf/v2` namespace is listed) but its REST API is off,
which is the default. Application-password auth is fine; the plugin refuses before
looking at it.

**Fix**. Forms → Settings → REST API → Enable access to the API. `WP.gf_state()` returns
`disabled` for exactly this case and `missing` when the plugin is not installed at all.
Gravity Forms is licensed and not on wordpress.org, so `install_plugin()` cannot fetch it.

---

## Gravity Forms: a notification was added instead of updated, or one vanished

**Cause**. `notifications` and `confirmations` are dicts on the form object keyed by a
13-character id, and `PUT /gf/v2/forms/{id}` replaces the whole form. Sending a new id adds
a notification; sending the form without the key drops every notification it held.

**Fix**. Read with `gf_form()`, edit the dicts in place, write back with `gf_update_form()`.
`launch.py` derives ids from the notification names (`stable_id()`), so its re-runs update
the same objects. Merge tags bind by field id (`{Email:3}`), so build them from the form
you read back, not from the order you think you created the fields in.

---

## Plugin install returns HTTP 500 but the plugin is there

Large plugins exceed the request timeout while unzipping. The files land; the response
fails. A retry then reports `folder_exists`.

**Fix**. Treat 500/`folder_exists` as "probably installed": re-read `GET /wp/v2/plugins`
and activate whatever is present. `WP.install_plugin()` implements this.

---

## Rank Math meta cannot be set over REST

`rank_math_title` / `rank_math_description` are not registered for REST until the setup
wizard has run, and even then may not be exposed.

**Workaround**. Rank Math's default description template falls back to the post excerpt,
which *is* a first-class REST field. Write excerpts and the descriptions appear.

Two manual steps remain: run the setup wizard, then **Settings → Permalinks → Save** to
flush rewrite rules, otherwise `/sitemap_index.xml` 404s.

---

## Scripted requests start returning 403

**Symptom**, curl/urllib worked, then every request returns 403 while a browser loads the
site fine.

**Cause**. Security plugins (SiteGround Security, Wordfence, …) rate-limit or block
non-browser user agents after repeated hits.

**Fix**. Send a real browser `User-Agent` (`scripts/verify.py` does), space out requests,
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

**Rule**. When a check disagrees with a manual inspection, suspect the checker. Print the
values it is actually comparing (`repr()`), and `od -c` the source line if a regex is
involved. Write files with the editor tools rather than shell heredocs when they contain
regex escapes.
