# -*- coding: utf-8 -*-
"""push_page() writes content then CSS, and falls back when css_settings dies.

The bug this pins: agents called update_page() (which clears _gspb_post_css)
and then set_post_css(), or the other way around, or they POSTed
/wp/v2/pages/{id}/meta which does not exist. Hosts that 403
greenshift/v1/css_settings looked like a total injection failure.

    python tests/test_push_page.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))

# wp_api.WP() reads env on init; give it dummy values before import side effects
os.environ.setdefault('WP_URL', 'https://example.com')
os.environ.setdefault('WP_USER', 'dev')
os.environ.setdefault('WP_APP_PASSWORD', 'xxxx xxxx xxxx xxxx xxxx xxxx')

from wp_api import (  # noqa: E402
    AUTH_FALLBACK_HEADER, POST_CSS_META, WPVIBE_AUTH_HEADER, WP, WPError,
    auth_headers, is_stripped_auth, reject_css_in_payload,
)


class FakeWP(WP):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.meta_status = None
        self.css_settings_status = None

    def post(self, route, payload):
        self.calls.append((route, payload))
        if route == 'greenshift/v1/css_settings' and self.css_settings_status:
            raise WPError(self.css_settings_status, 'blocked')
        if route.startswith('wp/v2/pages/') and isinstance(payload, dict) \
                and payload.get('meta') and self.meta_status:
            raise WPError(self.meta_status, 'blocked')
        if route.startswith('wp/v2/pages/') or route == 'wp/v2/pages':
            return {'id': payload.get('id', 20), 'link': 'https://example.com/x'}
        return {'ok': True}


def run():
    failures = 0

    def check(name, ok, detail=''):
        nonlocal failures
        print('%s %s' % ('ok  ' if ok else 'FAIL', name))
        if not ok:
            failures += 1
            if detail:
                print('       ' + detail)

    headers = auth_headers('abc123')
    check('auth_headers sends Authorization',
          headers.get('Authorization') == 'Basic abc123', str(headers))
    check('auth_headers sends X-Greenlight-Authorization',
          headers.get(AUTH_FALLBACK_HEADER) == 'Basic abc123', str(headers))
    check('auth_headers sends X-WPVibe-Authorization',
          headers.get(WPVIBE_AUTH_HEADER) == 'Basic abc123', str(headers))

    check('401 rest_not_logged_in is stripped auth',
          is_stripped_auth(401, '{"code":"rest_not_logged_in"}'))
    check('401 incorrect_password is not stripped auth',
          not is_stripped_auth(401, '{"code":"incorrect_password"}'))
    check('403 is not stripped auth',
          not is_stripped_auth(403, '{"code":"rest_forbidden"}'))

    try:
        reject_css_in_payload({'meta': {POST_CSS_META: '.x{}'}})
        check('reject_css_in_payload raises on meta', False)
    except ValueError as exc:
        check('reject_css_in_payload raises on meta', POST_CSS_META in str(exc), str(exc))

    html = '<!-- wp:greenshift-blocks/element {"id":"gsbp-aaaaaaa"} -->\n<div class="gsbp-aaaaaaa"></div>\n<!-- /wp:greenshift-blocks/element -->\n'

    wp = FakeWP()
    wp.push_page(20, content=html, css='.hero{color:red}')
    routes = [c[0] for c in wp.calls]
    page_calls = [c for c in wp.calls if c[0] == 'wp/v2/pages/20']
    check('update does not clear CSS',
          not any(c[0] == 'greenshift/v1/css_settings' and c[1].get('css') == ''
                  for c in wp.calls),
          str(wp.calls))
    check('content is written before CSS meta',
          len(page_calls) >= 2
          and 'content' in page_calls[0][1]
          and POST_CSS_META in (page_calls[1][1].get('meta') or {}),
          str(wp.calls))
    content_payload = page_calls[0][1]
    check('update payload has no status',
          'status' not in content_payload, str(content_payload))
    css_payload = page_calls[1][1]
    check('page meta got the stylesheet',
          css_payload.get('meta', {}).get(POST_CSS_META) == '.hero{color:red}',
          str(css_payload))

    wp = FakeWP()
    try:
        wp.update_page(20, content=html, meta={POST_CSS_META: '.x{}'})
        check('update_page refuses CSS meta', False)
    except ValueError as exc:
        check('update_page refuses CSS meta', POST_CSS_META in str(exc), str(exc))

    wp = FakeWP()
    wp.meta_status = 403
    wp.push_page(20, content=html, css='.hero{color:red}')
    css_calls = [c for c in wp.calls if c[0] == 'greenshift/v1/css_settings']
    check('403 on page meta falls back to css_settings',
          css_calls and css_calls[0][1].get('css') == '.hero{color:red}'
          and css_calls[0][1].get('id') == 20,
          str(wp.calls))

    wp = FakeWP()
    wp.push_page(content=html, css='.x{}', title='Home', slug='home')
    creates = [c for c in wp.calls if c[0] == 'wp/v2/pages']
    check('create uses POST /wp/v2/pages', bool(creates), str(wp.calls))
    check('create then stores CSS via meta',
          any(c[0].startswith('wp/v2/pages/') and (c[1].get('meta') or {}).get(POST_CSS_META)
              for c in wp.calls),
          str(wp.calls))

    print('\n%d failing case(s)' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(run())
