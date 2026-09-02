# -*- coding: utf-8 -*-
"""
Post-push verification for generated pages.

    python verify.py https://site.com/about/
    python verify.py --all                      # every published page

Checks the things that actually broke in practice:
  * page renders and is not a 403/404 wall
  * exactly one h1, and a heading outline with no skipped levels
  * every image has alt text and intrinsic width/height
  * every button/link has a discernible accessible name (the PSI "agent
    accessibility" audit), icon-only controls need aria-label
  * blocks got their CSS: `gsbp-` classes present AND matching CSS rules emitted
  * stylebook tokens resolved (no literal `var(--gt-` left unresolved in styles)

It does NOT replace a browser check for layout. Use the browser for responsive and
for anything JS-driven. This is the fast fail-early pass.
"""
import argparse
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


def fetch(url):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)          # security plugins 403 default UAs
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise SystemExit(
                f'{url} -> 403. A security plugin is rate-limiting scripted requests; '
                'verify in a browser instead (see reference/troubleshooting.md).')
        raise


def check(url):
    html = fetch(url)
    problems, notes = [], []

    if '<title>403' in html or 'Forbidden' in html[:400]:
        problems.append('page returned a block/deny wall rather than content')

    headings = re.findall(r'<(h[1-6])[^>]*>(.*?)</\1>', html, re.S | re.I)
    levels = [int(tag[1]) for tag, _ in headings]
    h1_count = levels.count(1)
    if h1_count != 1:
        problems.append(f'{h1_count} h1 elements (expected exactly 1), '
                        'check the page template is "no-title"')
    previous = 0
    for level in levels:
        if previous and level > previous + 1:
            problems.append(f'heading level jumps h{previous} -> h{level}')
            break
        previous = level
    notes.append('headings: ' + ' '.join(f'h{l}' for l in levels[:12]) +
                 (' …' if len(levels) > 12 else ''))

    images = re.findall(r'<img[^>]*>', html, re.I)
    no_alt = [i for i in images if not re.search(r'\balt=', i)]
    no_dims = [i for i in images if not (re.search(r'\bwidth=', i) and re.search(r'\bheight=', i))]
    if no_alt:
        problems.append(f'{len(no_alt)} image(s) without an alt attribute')
    if no_dims:
        problems.append(f'{len(no_dims)} image(s) without width/height (layout shift)')

    # Raster sources must be WebP. Image weight is normally the largest thing on
    # the page, and a single hand-uploaded PNG undoes the image pipeline.
    legacy = sorted({m.group(1) for i in images
                     for m in [re.search(r'src="([^"]+\.(?:png|jpe?g))(?:\?|")', i, re.I)]
                     if m})
    if legacy:
        problems.append(f'{len(legacy)} image(s) served as PNG/JPEG instead of WebP:')
        for src in legacy[:5]:
            problems.append('    ' + src.rsplit('/', 1)[-1])
        if len(legacy) > 5:
            problems.append(f'    …and {len(legacy) - 5} more')
        problems.append('    convert with scripts/prep_images.py, audit with '
                        '"prep_images.py audit"')
    notes.append(f'images: {len(images)}')

    # Fonts fail silently: a family installed but not activated on global styles
    # emits no @font-face and falls back to a system font with no error anywhere.
    faces = len(re.findall(r'@font-face', html))
    cdn = len(re.findall(r'fonts\.(?:googleapis|gstatic)\.com', html))
    notes.append('fonts: %d @font-face, %d Google CDN refs' % (faces, cdn))
    if faces == 0:
        problems.append('no @font-face in the page — either no webfont is loaded, or a '
                        'font family is installed but not activated on the global-styles '
                        'record, which is silent')

    # Core's flow margin puts 1.6rem between top-level sections, which reads as a
    # seam between adjacent full-bleed colour bands.
    if re.search(r'is-layout-flow\)\s*>\s*\*\s*\{[^}]*margin-block-start:\s*(?!0)', html):
        if not re.search(r'body\s+\.is-layout-flow\s*>\s*\*\s*\{[^}]*margin-block-start:\s*0',
                         html):
            problems.append("core's .is-layout-flow margin-block-start is active and not "
                            "overridden — adjacent full-width sections will show a seam. "
                            "Add `body .is-layout-flow > * { margin-block-start: 0 }`")

    nameless = []
    for match in re.finditer(r'<(a|button)\b([^>]*)>(.*?)</\1>', html, re.S | re.I):
        tag, attrs, inner = match.group(1), match.group(2), match.group(3)
        if re.search(r'aria-label=|aria-labelledby=|title=', attrs):
            continue
        # An <img alt> or <svg><title> inside the control supplies the name too.
        text = re.sub(r'<[^>]+>', '', inner).strip()
        img_alt = ' '.join(re.findall(r'<img[^>]*alt="([^"]+)"', inner, re.I))
        svg_title = ' '.join(re.findall(r'<title[^>]*>(.*?)</title>', inner, re.S | re.I))
        if not (text or img_alt.strip() or svg_title.strip()):
            snippet = (tag + attrs)[:90].replace('\n', ' ')
            nameless.append(snippet)
    if nameless:
        problems.append(f'{len(nameless)} link(s)/button(s) with no accessible name, '
                        'agents and screen readers cannot use them:')
        for snippet in nameless[:5]:
            problems.append(f'    <{snippet}…')

    block_classes = set(re.findall(r'class="[^"]*?(gsbp-[a-z0-9]{7})', html))
    styled = set(re.findall(r'\.(gsbp-[a-z0-9]{7})\s*\{', html))
    unstyled = block_classes - styled
    notes.append(f'blocks: {len(block_classes)}, with CSS: {len(styled)}')
    if block_classes and len(styled) == 0:
        problems.append('NO block CSS emitted, blocks are missing "CSSRender": true, '
                        'or stale _gspb_post_css is overriding (clear it via css_settings)')

    tokens = set(re.findall(r'(--gt-[a-z0-9-]+)\s*:', html))
    used = set(re.findall(r'var\((--gt-[a-z0-9-]+)', html))
    undefined = used - tokens
    if undefined:
        problems.append('CSS variables used but never defined: ' + ', '.join(sorted(undefined)))

    print(f'\n{url}')
    for note in notes:
        print('  ·', note)
    if problems:
        print('  FAIL')
        for problem in problems:
            print('   !', problem)
    else:
        print('  OK')
    return not problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*')
    parser.add_argument('--all', action='store_true', help='check every published page')
    args = parser.parse_args()

    urls = list(args.urls)
    if args.all or not urls:
        from wp_api import WP
        wp = WP()
        urls += [p['link'] for p in wp.get('wp/v2/pages?per_page=100&status=publish')]

    results = [check(u) for u in urls]   # evaluate all, do not short-circuit
    ok = all(results)
    print()
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
