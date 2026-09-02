# -*- coding: utf-8 -*-
"""
Link and anchor integrity across the whole site.

verify.py checks one page at a time and never looks at where a link points. Most
link defects only exist between pages, so they survive a clean verify.py run:

  * a menu still pointing at homepage anchors after the site grew past one page
    ("#weddings" works on the homepage and is dead on every other page)
  * a header CTA or skip link aimed at an id that exists on one page only
  * a menu item linking to a page that is still a draft, so visitors get a 404
  * absolute staging URLs baked into content, which all break on the domain move

Usage:
    python scripts/check_links.py            # every published page
    python scripts/check_links.py --slug faq
"""
import io
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wp_api import WP  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')

SKIP_SCHEMES = ('mailto:', 'tel:', 'javascript:', 'data:', 'sms:')
# WordPress emits these itself; they are not the build's links to get wrong.
IGNORE = re.compile(r'/(wp-json|wp-content|wp-includes|xmlrpc\.php|feed)|/comments/feed')


def fetch(url):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode('utf-8', 'replace')


def status(url, cache={}):
    if url not in cache:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', UA)
        try:
            cache[url] = urllib.request.urlopen(req, timeout=30).getcode()
        except urllib.error.HTTPError as exc:
            cache[url] = exc.code
        except Exception as exc:                      # DNS, TLS, timeout
            cache[url] = type(exc).__name__
    return cache[url]


def body_of(html):
    """Strip <head> so canonical/og/alternate URLs are not counted as content links."""
    return re.sub(r'<head\b.*?</head>', '', html, flags=re.S | re.I)


def main():
    wp = WP()
    base = wp.url.rstrip('/')
    host = urllib.parse.urlparse(base).netloc

    pages = wp.get('wp/v2/pages?per_page=100&status=any&context=edit')
    published = {p['slug']: p for p in pages if p['status'] == 'publish'}
    drafts = {p['slug']: p for p in pages if p['status'] != 'publish'}

    only = None
    if '--slug' in sys.argv:
        only = sys.argv[sys.argv.index('--slug') + 1]

    problems, absolute, navs = [], 0, {}

    for slug, page in sorted(published.items()):
        if only and slug != only:
            continue
        html = fetch(page['link'])
        body = body_of(html)
        ids = set(re.findall(r'\bid="([^"]+)"', html))

        nav = re.search(r'<nav[^>]*aria-label="Main"[^>]*>.*?</nav>', html, re.S | re.I)
        if nav:
            navs[slug] = tuple(sorted(set(re.findall(r'href="([^"]+)"', nav.group(0)))))

        for href in sorted(set(re.findall(r'href="([^"]+)"', body))):
            if href.startswith(SKIP_SCHEMES) or IGNORE.search(href):
                continue

            # in-page anchor: the id has to exist on THIS page
            if href.startswith('#'):
                if href != '#' and href[1:] not in ids:
                    problems.append(f'{slug}: dead anchor {href} (no matching id on the page)')
                continue

            if href.startswith('/'):
                target = urllib.parse.urljoin(base + '/', href)
            elif href.startswith(base):
                absolute += 1
                target = href
            elif href.startswith(('http://', 'https://')):
                continue                              # external, not ours to police
            else:
                target = urllib.parse.urljoin(page['link'], href)

            path, _, frag = target.partition('#')
            code = status(path)
            if code != 200:
                # a link to a page we know is a draft is worth naming precisely
                hit = next((s for s in drafts if f'/{s}/' in path), None)
                why = f'page "{hit}" is a draft' if hit else f'HTTP {code}'
                problems.append(f'{slug}: broken link {href} ({why})')
            elif frag:
                try:
                    if frag not in set(re.findall(r'\bid="([^"]+)"', fetch(path))):
                        problems.append(
                            f'{slug}: {href} resolves but #{frag} does not exist there')
                except Exception:
                    pass

    if len(set(navs.values())) > 1:
        problems.append('main nav is not identical across pages:')
        for slug, items in sorted(navs.items()):
            problems.append(f'    {slug}: {list(items)}')

    print(f'{len(navs)} published page(s) checked against {host}')
    if absolute:
        print(f'\nNOTE: {absolute} internal link(s) use the absolute {base} URL. They work '
              f'now and every one of them breaks on the domain move. Root-relative '
              f'("/slug/") is the fix; schema and og: URLs must stay absolute.')
    if problems:
        print(f'\n{len(problems)} PROBLEM(S):')
        for p in problems:
            print('  ' + p)
        return 1
    print('\nno broken links, no dead anchors, nav consistent')
    return 0


if __name__ == '__main__':
    sys.exit(main())
