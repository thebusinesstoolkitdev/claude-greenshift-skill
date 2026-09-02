# -*- coding: utf-8 -*-
"""
Thin WordPress / Greenshift / Gravity Forms REST client.

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
import io
import json
import os
import time
import urllib.error
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')


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


def encode_webp(img, quality=82):
    """Encode to WebP, keeping whichever of lossy or lossless comes out smaller.

    Fixed lossy quality is the obvious default and it is wrong for a whole class
    of images every site has: logos, screenshots, diagrams, flat illustrations,
    anything with large flat areas and hard edges. Lossy encoders spend bytes on
    the edges they cannot represent, so a 79kB PNG logo can come back as a 153kB
    WebP, a real regression dressed up as an optimisation. Photographs go the
    other way and compress far better lossy.

    Trying both costs one extra encode and removes the guesswork. Returns
    (bytes, description) so the caller can report which mode won.
    """
    import io as _io
    out = []
    for how, kw in (('lossy q%d' % quality, {'quality': quality, 'method': 6}),
                    ('lossless', {'lossless': True, 'method': 6})):
        buf = _io.BytesIO()
        try:
            img.save(buf, 'WEBP', **kw)
        except Exception:
            continue
        out.append((len(buf.getvalue()), how, buf.getvalue()))
    if not out:
        raise ValueError('WebP encoding failed for this image')
    size, how, data = min(out, key=lambda t: t[0])
    return data, how


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
        """route is relative to /wp-json/, e.g. 'wp/v2/pages/12?context=edit'."""
        url = f'{self.url}/wp-json/{route.lstrip("/")}'
        data = raw_body if raw_body is not None else (
            json.dumps(payload).encode() if payload is not None else None)
        req = urllib.request.Request(
            url, data=data, method=method or ('POST' if data is not None else 'GET'))
        req.add_header('Authorization', 'Basic ' + self.auth)
        # Cloudflare and most security plugins 403 the default Python-urllib
        # agent, which fails on the very first call of a build.
        req.add_header('User-Agent', UA)
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
        # Several Greenshift endpoints return a JSON-encoded *string*.
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
            'gravityforms': self.gf_state(namespaces),
            'namespaces': namespaces,
        }

    @staticmethod
    def _encode_webp(img):
        return encode_webp(img)

    def upload_media(self, path, mime=None, keep_format=False):
        """Upload a local file to the media library. Returns the attachment object.

        Raster sources are converted to WebP first. Image weight is usually the
        largest thing on the page, WebP is 25-35% smaller than JPEG at the same
        quality, and a single stray PNG uploaded by hand undoes the whole image
        pipeline. Conversion happens here, at the only door into the library, so
        it cannot be skipped by accident.

        SVG passes through untouched (vector, nothing to convert). GIF passes
        through because converting drops the animation. Pass keep_format=True for
        a genuine exception, such as a source a third party requires verbatim.
        """
        raster = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')
        filename = os.path.basename(path)
        stem, ext = os.path.splitext(filename)
        data = None

        if ext.lower() in raster and not keep_format:
            try:
                from PIL import Image
            except ImportError:
                raise SystemExit(
                    f'{filename} is {ext.lstrip(".").upper()} and must be WebP before '
                    'upload, but Pillow is not installed.\n'
                    '  pip install Pillow      then: python scripts/prep_images.py build\n'
                    'Pass keep_format=True only if the original format is genuinely '
                    'required.')
            img = Image.open(path)
            img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')
            data, how = encode_webp(img)
            before = os.path.getsize(path)
            grew = '. LARGER than the source, check this one' if len(data) > before else ''
            print(f'  converted {filename} -> {stem}.webp '
                  f'({before // 1024}kB -> {len(data) // 1024}kB, {how}){grew}')
            filename, mime = stem + '.webp', 'image/webp'

        if mime is None:
            mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                    'webp': 'image/webp', 'gif': 'image/gif',
                    'svg': 'image/svg+xml'}.get(
                        filename.rsplit('.', 1)[-1].lower(), 'application/octet-stream')
        if data is None:
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

    def update_page(self, page_id, content=None, clear_css=True, **extra):
        payload = dict(extra)
        if content is not None:
            payload['content'] = content
        page = self.post(f'wp/v2/pages/{page_id}', payload)
        if content is not None and clear_css:
            # Only valid on the CSSRender path, where the server compiles CSS from
            # block attributes and stale meta would shadow it. On the documented
            # page path this field IS the page's stylesheet, so clearing it here
            # wipes what set_post_css() just wrote. Pass clear_css=False, or call
            # set_post_css() after this.
            self.clear_post_css(page_id)
        return page

    def clear_post_css(self, post_id):
        """Remove stale _gspb_post_css meta left behind by editor saves."""
        return self.post('greenshift/v1/css_settings', {'id': post_id, 'css': ''})

    def set_block_js(self, scripts):
        """Register block scripts in the `gspb_block_js` option.

        Greenshift reads frontend scripts from that option, not from post
        content, and the editor is what normally writes it. Blocks inserted
        programmatically carry `customJs` that never runs until this is called.

        `scripts` maps block id to code: {"gsbp-abc1234": "console.log(1)"}.
        The endpoint merges into the existing option; an empty value removes a
        key. `{{PLUGIN_URL}}` placeholders are resolved by PHP at render time,
        so leave them intact here.

        This is upstream's Option B. Option A is WP-CLI `wp option update
        gspb_block_js`. Option C, which this skill uses by default, is to drop
        the script into a `wp:html` block at the end of the page instead: no
        option write, no manage_options capability, and it survives a host that
        blocks the endpoint. On that path `{{PLUGIN_URL}}` must be replaced with
        the real path, because raw wp:html output is never processed by PHP.
        """
        payload = [{block_id: code} for block_id, code in scripts.items()]
        return self.post('greenshift/v1/update-custom-js', {'js': payload})

    def set_post_css(self, post_id, css):
        """Write a page's compiled CSS to _gspb_post_css.

        This is the documented contract for pages and posts, which do not carry
        CSSRender. Pair it with blocks.compile_css() over the markup you pushed:

            html = build_page()
            wp.update_page(pid, content=html)
            wp.set_post_css(pid, blocks.compile_css(html))
        """
        return self.post('greenshift/v1/css_settings', {'id': post_id, 'css': css})

    # ---------- template parts ----------

    def template_parts(self):
        """Every template part the active theme exposes, with `area` and `source`."""
        return self.get('wp/v2/template-parts?context=edit')

    def find_template_part(self, area):
        """Resolve (theme, slug) for the part filling `area` ('header', 'footer').

        Any FSE theme, not only Greenlight: the slug is read from the site rather
        than assumed. A customised copy (source "custom") wins over the theme
        file, and an exact slug match wins over another part in the same area.
        """
        parts = self.template_parts()
        hits = [p for p in parts if p.get('area') == area] or \
               [p for p in parts if p.get('slug') == area]
        if not hits:
            raise LookupError('no template part with area or slug %r; found %s'
                              % (area, sorted(p.get('slug') for p in parts)))
        hits.sort(key=lambda p: (p.get('slug') != area, p.get('source') != 'custom'))
        return hits[0]['theme'], hits[0]['slug']

    def get_template_part(self, theme=None, slug=None, area=None):
        """Read a template part by (theme, slug), or by area= to discover both."""
        if area:
            theme, slug = self.find_template_part(area)
        return self.get(f'wp/v2/template-parts/{theme}//{slug}?context=edit')

    def set_template_part(self, theme=None, slug=None, content=None, area=None):
        if area:
            theme, slug = self.find_template_part(area)
        if content is None:
            raise ValueError('set_template_part needs content')
        return self.post(f'wp/v2/template-parts/{theme}//{slug}', {'content': content})

    # ---------- global styles (theme.json user record) ----------

    def global_styles_id(self):
        """Id of the user-level global-styles record for the active theme.

        `wp/v2/global-styles/themes/{slug}` returns the theme's own data without
        an id; the editable record is linked from the theme itself.
        """
        theme = self.get('wp/v2/themes?status=active')[0]
        href = theme['_links']['wp:user-global-styles'][0]['href']
        return int(href.rstrip('/').rsplit('/', 1)[-1])

    def global_styles(self):
        return self.get('wp/v2/global-styles/%d?context=edit' % self.global_styles_id())

    def set_global_styles(self, settings=None, styles=None):
        """Write settings and/or styles on the user record. Each is replaced whole,
        so read with global_styles(), merge locally, then write."""
        payload = {}
        if settings is not None:
            payload['settings'] = settings
        if styles is not None:
            payload['styles'] = styles
        return self.post('wp/v2/global-styles/%d' % self.global_styles_id(), payload)

    # ---------- Greenshift stylebook ----------

    def gs_settings(self):
        """Current Greenshift global settings dict (stylebook).

        Writes go to `global_settings`; reads come from `figma_settings`, which
        is the endpoint upstream documents for reading and the one that returns
        the stored variables and classes. A GET on `global_settings` answers with
        empty lists for both while the front end renders them, so verify against
        the wrong endpoint reported 0/0 on a populated stylebook.
        """
        # GETs on these routes are served from the host's page cache for a while
        # after a write, answering with the previous (often empty) lists; a unique
        # query string reads the live record
        bust = '?_=%d' % int(time.time() * 1000)
        for route in ('greenshift/v1/figma_settings', 'greenshift/v1/global_settings'):
            try:
                data = self.get(route + bust)
            except WPError:
                continue
            settings = data.get('settings') if isinstance(data, dict) else None
            if isinstance(settings, str):
                settings = json.loads(settings)
            if settings and (settings.get('variables') or settings.get('global_classes')):
                return settings
            last = settings or {}
        return last

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

        Large plugins often time out with HTTP 500 while the files land fine. This
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

    # ---------- Gravity Forms (REST API v2) ----------
    #
    # Licensed plugin, not on wordpress.org: upload once, enter the licence, and
    # enable the API under Forms -> Settings -> REST API. Application passwords
    # authenticate; the user's Gravity Forms capabilities are honoured. Forms are
    # whole objects: fields, notifications and confirmations travel together, and
    # PUT replaces the object, so read, edit, write back.

    def gf_state(self, namespaces=None):
        """'ready', 'disabled' (plugin active, REST switched off), or 'missing'."""
        if namespaces is None:
            namespaces = self.get('').get('namespaces', [])
        if 'gf/v2' not in namespaces:
            return 'missing'
        try:
            self.get('gf/v2/forms')
        except WPError as exc:
            if exc.status in (401, 403):
                return 'disabled'
            raise
        return 'ready'

    def gf_forms(self):
        """Every form as a list of {id, title, entries}. The endpoint answers with an
        object keyed by form id; this flattens it."""
        data = self.get('gf/v2/forms')
        if isinstance(data, dict):
            return [v if isinstance(v, dict) else {'id': k} for k, v in data.items()]
        return data or []

    def gf_form(self, form_id):
        return self.get(f'gf/v2/forms/{form_id}')

    def gf_create_form(self, form):
        return self.post('gf/v2/forms', form)

    def gf_update_form(self, form_id, form):
        """Replace the whole form object. Pass what gf_form() returned, edited."""
        return self.request(f'gf/v2/forms/{form_id}', form, method='PUT')

    def gf_delete_form(self, form_id, force=False):
        """Trash a form; force=True deletes it permanently."""
        return self.delete(f'gf/v2/forms/{form_id}' + ('?force=true' if force else ''))

    def gf_entries(self, form_id, page_size=20):
        return self.get(f'gf/v2/forms/{form_id}/entries?paging[page_size]={page_size}')

    def gf_submit(self, form_id, values):
        """Submit values ({field_id: value}) as a real submission. This creates an
        entry and fires notifications, so it is a live test, not a probe."""
        payload = {f'input_{k}': v for k, v in values.items()}
        return self.post(f'gf/v2/forms/{form_id}/submissions', payload)
