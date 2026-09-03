# Site conventions

Things that are true of any website, learned the expensive way on builds that passed every
mechanical check and were still wrong. `SKILL.md` covers Greenshift and the REST API; this
covers the site.

---

## Typography: cap the measure or the design collapses

**Every prose class needs a `max-width`.** A body class with colour, size and line-height but
no measure looks correct in a two-column layout and falls apart the moment the same class is
used full-width, where the line runs 180 characters. The page reads as unstyled, and the
instinct is to blame the CSS pipeline rather than the missing property.

```css
.gt-lead      { max-width: 68ch; text-wrap: pretty; }
.gt-body-copy { max-width: 72ch; text-wrap: pretty; }
```

65-75ch. Also `text-wrap: balance` on `h1` to `h3` so headings break evenly instead of leaving
one orphaned word.

This is the highest-value line in this document. It is invisible until it is catastrophic.

## Layout: no single-column content sections

A full-width section holding one centred column of text is the default that reads as a
template. Pair prose with something: an image, a spec list, a set of cards. When a section
genuinely has one idea, constrain it (`max-width` plus margin) rather than letting it span.

**Six items go in a 3×2 grid, not six alternating full-width rows.** Alternating
image/text rows are a legitimate pattern for three or four items with real narrative order.
Past that they are ~400px of scrolling each, and the reader is scrolling to find the list
they could have scanned. If the same items already appear as a grid elsewhere on the site,
match that.

Avoid splitting one list across two columns. Reading order goes down, then across, and
nobody reads that way. An FAQ accordion is one column, constrained to about 860px.

## Links

**Internal links are root-relative.** `/pricing/` not `https://staging.example.com/pricing/`.
Absolute links to the build host work perfectly until the domain moves, then every one of
them is wrong. Schema `@id`/`url`, `og:` tags and canonicals must stay absolute; those are
generated from a single constant, so the migration is one edit.

**In-page anchors are page-local.** A header CTA pointing at `#contact-form` works on the
page that has the form and is dead everywhere else. Point cross-page links at `/#contact-form`
so the anchor resolves after navigation. Same for "skip to content": target an id the theme
emits on every page, not one that exists on the homepage only.

**A menu built once for a one-page site is wrong the day a second page exists.** Anchors like
`#services` silently stop working on every new page. Rebuild the menu against real slugs.

**Never link to a draft.** Build the menu from pages that are actually published so an
unfinished page cannot 404 a visitor:

```python
live = {p['slug'] for p in wp.get('wp/v2/pages?per_page=100&status=publish')}
items = [(label, f'/{slug}/') for label, slug in NAV if slug in live]
```

`python scripts/check_links.py` checks all of this across the site. `verify.py` does not. It
reads one page at a time and never follows a link.

## Titles: the post title and the search title are different jobs

The WordPress post title is what a human sees: the admin page list, the menu, breadcrumbs.
The search title is what Google shows. Putting the keyword-loaded string in the post title
makes the client's page list unreadable and puts keyword soup in the navigation.

| Post title | Rank Math title |
|---|---|
| `Packages` | `Wedding Bartender Packages from $1,000 \| Brand` |
| `Meet the team` | `Meet the Team \| Brand, Southern California` |

Keep search titles under ~60 characters and descriptions under ~155 so neither is truncated.

Define them in **one** place. When several generators each write `rank_math_*` for their own
pages, the values drift and nobody can find the one that is live. One module owns the table;
the generators own the content.

`rank_math_*` is not exposed through `wp/v2/pages` meta, so it cannot be read back. Verify by
fetching the live page and reading the rendered `<title>`, never by trusting the write.

## Content

Publish real figures. Comparing pages that rank against pages that do not, the differentiator
is concreteness, not length: a page that states a starting price, a per-person figure, a
duration and a capacity outranks a longer page that says "contact us for a quote". Where a
number cannot be published, publish the range and what moves it.

Answer questions in the words people search. A heading phrased as the actual question, with a
direct answer in the first sentence beneath it, is extractable by AI overviews and featured
snippets. Prose that circles the answer is not.

Say what is *not* included. It removes the objection and it is the section competitors omit.

## Updating pages without destroying them

**Never send `status` on a content update.** A push helper that always sends
`status: "draft"` will unpublish a live page the first time it is run against production.
Send status only when deliberately changing it:

```python
payload = {'content': html}                  # not 'status'
if creating:
    payload['status'] = 'draft'
```

Read back the status after any bulk update. A REST write can flip a draft to published as a
side effect, and nothing warns you.

Before a bulk push, print what will change and against which page ids. Slug collisions and a
stale id map are how the wrong page gets overwritten.

## The stylebook is the only place styles live

Removing a class from the local definition does not remove it from the site, the push
replaces the array it sends, so a class you stopped defining just stays. Prune explicitly:
read the stored classes, keep the ones outside your prefix, and drop the prefixed ones no
longer defined.

When something is not styling, check whether the class is still on the server before
debugging the CSS.

## Browser automation lies in a headless pane

A preview pane that does not composite reports confident, wrong answers:

- `requestAnimationFrame` never fires, anything gated on it never runs
- IntersectionObserver never fires, reveal-on-scroll content stays hidden
- CSS transitions and animations never advance, a panel that opens by animation reads shut
- `scrollY` stays 0, sticky and scroll-progress behaviour looks broken
- `srcset` is resolved at the viewport at parse time, resizing does not re-pick, so an
  image "loads the wrong size" only because the page was not reloaded after the resize

Reload at the target viewport, force the end state directly, and confirm on a real device
before reporting any of these as a bug. Three separate "bugs" on one build were all this.

## Handover

Every domain-dependent value is a migration item: absolute links, form confirmation
redirects, sitemap URLs, schema `@id`, hardcoded hosts in scripts. Collect them while
building rather than hunting them afterwards.

Leave the client something they can edit. A section built as raw markup, a hardcoded list, a
value duplicated across five pages. Each is a support call. If a change belongs to the
client, it belongs in a block they can open.

## Contact details

Phone, email and address lines are **one element per line, each its own block**, inside an
`<address>` (or a `<ul>` when there are three or more), stacked with flex `row-gap`. Never
a paragraph with `<br>` between links: the break is presentational, a screen reader
announces one run-on sentence, and the client cannot reorder or remove a line in the
editor. The converter reproduces whatever the design HTML does, so fix the HTML source
first when converting; `blocks.contact_lines()` emits the right shape when generating.
`tel:` links carry the full international number; the visible text keeps the local format.
