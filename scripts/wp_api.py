# -*- coding: utf-8 -*-
"""
Thin WordPress / Greenshift / Fluent Forms REST client.

Reads credentials from environment or a .env file in the current working directory:

    WP_URL=https://site.com
    WP_USER=admin@example.com
    WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
    FIGMA_TOKEN=figd_...            # optional, Figma input only

Usage:
    from wp_api import WP
    wp = WP()                       # or WP(url=..., user=..., app_password=...)
    wp.get('wp/v2/pages')
    wp.post('wp/v2/pages', {'title': 'Home', 'status': 'draft', 'content': html})
    wp.gs_settings()                # Greenshift global settings (stylebook)
"""
import base64
import json
import os
import urllib.error
import urllib.request


def load_env(path='.env'):
    """Load KEY=VALUE lines from a .env file into os.environ (does not overwrite existing)."""
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip())


class WPError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f'HTTP {status}: {body[:400]}')


class WP:
    def __init__(self, url=None, user=None, app_password=None, timeout=180):
        load_env()
        self.url = (url or os.environ.get('WP_URL', '')).rstrip('/')
        user = user or os.environ.get('WP_USER', '')
        app_password = app_password or os.environ.get('WP_APP_PASSWORD', '')
        if not (self.url and user and app_password):
            raise SystemExit('Missing WP_URL / WP_USER / WP_APP_PASSWORD (env or .env)')
        self.auth = base64.b64encode(f'{user}:{app_password}'.encode()).decode()
        self.timeout = timeout

    # ---------- core ----------

    def request(self, route, payload=None, method=None, raw_body=None, headers=None):
        """route is relative to /wp-json/ — e.g. 'wp/v2/pages/12?context=edit'."""
        url = f'{self.url}/wp-json/{route.lstrip("/")}'
        data = raw_body if raw_body is not None else (
            json.dumps(payload).encode() if payload is not None else None)
        req = urllib.request.Request(
            url, data=data, method=method or ('POST' if data is not None else 'GET'))
        req.add_header('Authorization', 'Basic ' + self.auth)
        if raw_body is None:
            req.add_header('Content-Type', 'application/json')
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as exc:
            raise WPError(exc.code, exc.read().decode('utf-8', 'replace')) from None
        if not body:
            return None
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return body
        # Several Greenshift/Fluent endpoints return a JSON-encoded *string*.
        return json.loads(parsed) if isinstance(parsed, str) else parsed

    def get(self, route):
        return self.request(route)

    def post(self, route, payload):
        return self.request(route, payload)

    def delete(self, route, payload=None):
        return self.request(route, payload, method='DELETE')

    # ---------- convenience ----------

    def whoami(self):
        return self.get('wp/v2/users/me?context=edit')

    def check(self):
        """Verify auth + required plugins. Returns a dict summary; raises on hard failure."""
        me = self.whoami()
        root = self.get('')
        namespaces = root.get('namespaces', [])
        return {
            'user': me.get('username'),
            'roles': me.get('roles'),
            'is_admin': 'administrator' in me.get('roles', []),
            'greenshift': 'greenshift/v1' in namespaces,
            'fluentform': 'fluentform/v1' in namespaces,
            'namespaces': namespaces,
        }

    def upload_media(self, path, mime=None):
        """Upload a local file to the media library. Returns the attachment object."""
        filename = os.path.basename(path)
        if mime is None:
            ext = filename.rsplit('.', 1)[-1].lower()
            mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                    'webp': 'image/webp', 'svg': 'image/svg+xml'}.get(ext, 'application/octet-stream')
        with open(path, 'rb') as fh:
            data = fh.read()
        return self.request('wp/v2/media', raw_body=data, method='POST', headers={
            'Content-Type': mime,
            'Content-Disposition': f'attachment; filename="{filename}"',
        })

    # ---------- pages ----------

    def create_page(self, title, slug, content, status='draft', template='no-title', **extra):
        payload = {'title': title, 'slug': slug, 'status': status,
                   'content': content, 'template': template}
        payload.update(extra)
        return self.post('wp/v2/pages', payload)

    def update_page(self, page_id, content=None, **extra):
        payload = dict(extra)
        if content is not None:
            payload['content'] = content
        page = self.post(f'wp/v2/pages/{page_id}', payload)
        if content is not None:
            # Drop editor-compiled CSS so server-side CSSRender takes over.
            self.clear_post_css(page_id)
        return page

    def clear_post_css(self, post_id):
        """Remove stale _gspb_post_css meta left behind by editor saves."""
        return self.post('greenshift/v1/css_settings', {'id': post_id, 'css': ''})

    # ---------- template parts ----------

    def get_template_part(self, theme, slug):
        return self.get(f'wp/v2/template-parts/{theme}//{slug}?context=edit')

    def set_template_part(self, theme, slug, content):
        return self.post(f'wp/v2/template-parts/{theme}//{slug}', {'content': content})

    # ---------- Greenshift stylebook ----------

    def gs_settings(self):
        """Current Greenshift global settings dict (stylebook)."""
        data = self.get('greenshift/v1/global_settings')
        settings = data.get('settings') if isinstance(data, dict) else None
        if isinstance(settings, str):
            settings = json.loads(settings)
        return settings or {}

    def gs_merge(self, **keys):
        """
        Merge top-level stylebook keys (variables, colours, global_classes, elements).

        NOTE: each key you send REPLACES the stored value wholesale, so always read
        current settings, merge locally, then send the full array. This helper does
        the read for you only when you pass callables.
        """
        payload = {}
        current = None
        for key, value in keys.items():
            if callable(value):
                current = current if current is not None else self.gs_settings()
                payload[key] = value(current.get(key) or [])
            else:
                payload[key] = value
        return self.post('greenshift/v1/global_settings', payload)

    def gs_upsert_classes(self, new_classes):
        """Add or replace global classes by their `value` key, preserving the rest."""
        def merge(existing):
            index = {c.get('value'): i for i, c in enumerate(existing)}
            for cls in new_classes:
                if cls['value'] in index:
                    existing[index[cls['value']]] = cls
                else:
                    existing.append(cls)
            return existing
        return self.gs_merge(global_classes=merge)

    def gs_upsert_variables(self, new_variables):
        """Add or update CSS variables by their `variable` key."""
        def merge(existing):
            index = {v.get('variable'): i for i, v in enumerate(existing)}
            for var in new_variables:
                if var['variable'] in index:
                    existing[index[var['variable']]] = var
                else:
                    existing.append(var)
            return existing
        return self.gs_merge(variables=merge)

    # ---------- plugins ----------

    def install_plugin(self, slug, activate=True):
        """
        Install (and optionally activate) a wordpress.org plugin.

        Large plugins often time out with HTTP 500 while the files land fine — this
        retries activation and reports the real state instead of failing.
        """
        try:
            self.post('wp/v2/plugins', {'slug': slug, 'status': 'active' if activate else 'inactive'})
        except WPError as exc:
            if 'folder_exists' not in exc.body and exc.status != 500:
                raise
        installed = {p['plugin'].split('/')[0]: p for p in self.get('wp/v2/plugins')}
        entry = installed.get(slug)
        if entry is None:
            raise WPError(500, f'{slug} did not install')
        if activate and entry['status'] != 'active':
            entry = self.post('wp/v2/plugins/' + entry['plugin'], {'status': 'active'})
        return entry

    # ---------- Fluent Forms ----------

    def ff_forms(self):
        return self.get('fluentform/v1/forms')

    def ff_settings(self, form_id, meta_key):
        return self.get(f'fluentform/v1/settings/{form_id}?meta_key={meta_key}')

    def ff_save_setting(self, form_id, meta_key, value, meta_id=None):
        """
        Save a form setting.

        CRITICAL: pass meta_id to UPDATE an existing row. Without it Fluent Forms
        INSERTS a duplicate row, and duplicate settings rows produce unpredictable
        behaviour (e.g. two notifications, or the old confirmation still winning).
        """
        payload = {'meta_key': meta_key, 'value': json.dumps(value)}
        if meta_id is not None:
            payload['meta_id'] = meta_id
        return self.post(f'fluentform/v1/settings/{form_id}', payload)
