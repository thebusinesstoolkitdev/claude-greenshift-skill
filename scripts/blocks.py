# -*- coding: utf-8 -*-
"""
Greenlight block markup builder.

Emits Gutenberg block markup that survives block validation and renders correctly
when pushed over the REST API, from one set of calls, against either engine:

    greenshift  `wp:greenshift-blocks/element`. One element block per node, with
                per-block CSS compiled server-side. Needs the Greenshift plugin.
    core        native WordPress blocks (`wp:group`, `wp:heading`, `wp:paragraph`,
                `wp:list`, `wp:image`). No plugin needed; styling comes from
                stylebook classes and theme.json rather than per-block CSS.

Generators call `block()`, `grid()`, `heading()` and friends and do not care which
engine is underneath. Pick one with `set_backend('core')` or the GREENLIGHT_BACKEND
environment variable. Greenshift stays the default because it is what existing
builds use; `core` is the way off the plugin dependency.

The one real difference to plan for: Greenshift carries arbitrary CSS per block,
core does not. The core backend accepts the spacing/colour/typography subset that
core genuinely supports and refuses the rest, pointing you at a stylebook class.
That is the same thing this skill already tells you to do for breakpoints, so a
generator written to the house style ports with little friction.

The Greenshift rules below apply to that backend and are baked in:

1. CSSRender. On a template target every block carrying styleAttributes gets
   `"CSSRender": "1"` (the string, not a boolean) so the SERVER compiles its CSS;
   REST-pushed blocks never get editor-compiled CSS. On a page target no block
   carries it and the page's CSS goes to _gspb_post_css instead. Never add it to
   a block you did not author: the theme's blocks ship styleAttributes next to
   compiled inlineCssStyles, and re-emitting the raw values overrides them.
2. Escaped dashes. HTML comments cannot contain `--`, so CSS custom properties are
   escaped to \\u002d\\u002d inside the block JSON.
3. Declared attributes, any data-*/aria-*/role attribute must appear BOTH in the
   block JSON (`dynamicAttributes`) and in the HTML. Raw-only attributes fail block
   validation, Gutenberg offers "Attempt recovery", and recovery strips them.

styleAttributes values are responsive arrays,
["desktop","tablet","mobile_landscape","mobile_portrait"], fewer entries applying
upward. Multi-value arrays are safe over REST: verified against Greenlight 2.1 /
gl-page-builder 3.3.7 with `scripts/probe_responsive.py`, which pushes every shape
(1-4 entries, null and "" gaps, gridTemplateColumns) and reads the compiled CSS
back. The PHP renderer emits max-width rules at the BREAKPOINTS below and
`compile_css()` mirrors it for page targets. The core backend has no per-block
breakpoints at all, so a multi-value array raises there and the breakpoint goes in
a stylebook class.

`type` is always emitted, one of "text" / "inner" / "no", matching upstream's
converter. Images and empty elements are "no".
"""
import hashlib
import json
import os
import re

DASH = '\\u002d\\u002d'  # escaped `--` for use inside block-comment JSON

BACKEND = os.environ.get('GREENLIGHT_BACKEND', 'greenshift')
BACKENDS = ('greenshift', 'core')

# Upstream is explicit that this is the string "1", not a boolean:
# instructions/validate-styles.md and SKILL.md line 259. A boolean happens to
# work against the PHP renderer, which is how the wrong value survived.
CSSRENDER = '1'

# Greenshift's responsive breakpoints, in styleAttributes array order. Index 0 is
# desktop (no media query). Read off the PHP renderer's own output; if a probe
# against a newer plugin shows different values, change them here only.
BREAKPOINTS = (None, '991.98px', '767.98px', '575.98px')

# Where the markup is going. Upstream splits the CSS contract by target:
#   template  patterns, template parts, templates -> CSSRender on every block
#             carrying styleAttributes or dynamicGClasses
#   page      pages, posts, custom post types -> NO CSSRender; the page's CSS
#             goes into the _gspb_post_css meta field as one string
# SKILL.md:259: "Do not use CSSRender for blocks that will be saved in pages or
# posts". Header and footer are template parts, so they keep CSSRender.
TARGET = os.environ.get('GREENLIGHT_TARGET', 'template')
TARGETS = ('template', 'page')


def set_target(name):
    global TARGET
    if name not in TARGETS:
        raise ValueError('target must be one of %s, got %r' % (TARGETS, name))
    TARGET = name
    return TARGET

# Attributes Greenshift writes into the HTML from its own JSON keys, so they do
# not need declaring. `id` is deliberately absent: it comes from `anchor`.
# Anything not on this list must go into dynamicAttributes or the block fails
# validation and Attempt recovery silently deletes it.
_RENDERED_ATTRS = frozenset({
    'class', 'href', 'src', 'alt', 'title', 'width', 'height', 'loading',
    'target', 'rel', 'poster', 'controls', 'loop', 'autoplay', 'muted',
    'playsinline', 'colspan', 'rowspan', 'viewBox',
})


def set_backend(name):
    """Choose the block engine for everything emitted after this call."""
    global BACKEND
    if name not in BACKENDS:
        raise ValueError('backend must be one of %s, got %r' % (BACKENDS, name))
    BACKEND = name
    return BACKEND

_used_ids = set()
_id_cache = {}



def make_id(seed, prefix=''):
    """Deterministic 7-char block id from a seed string.

    Greenshift targets its compiled CSS at a `gsbp-` class, so that prefix is not
    optional on that backend. Core blocks have no such requirement, so they get a
    neutral `gl-` and carry no Greenshift naming at all.
    """
    key = BACKEND + '|' + prefix + seed
    if key in _id_cache:
        return _id_cache[key]
    stub = 'gl-' if BACKEND == 'core' else 'gsbp-'
    digest = hashlib.md5((prefix + seed).encode()).hexdigest()
    for i in range(25):
        candidate = stub + digest[i:i + 7]
        if candidate not in _used_ids:
            _used_ids.add(candidate)
            _id_cache[key] = candidate
            return candidate
    raise RuntimeError('could not allocate unique block id for ' + seed)


# kept so existing generators keep importing cleanly after the rename
gsid = make_id
block_id_for = make_id


class _RawJSON(str):
    """A string already carrying its own escape sequences.

    The icon spec wants literal \\u003c in the JSON, but json.dumps would escape the
    backslash and emit \\\\u003c, which the plugin then reads as text. This marks a
    value to be substituted in verbatim after encoding.
    """


def _encode(obj):
    raw = {}

    def swap(node):
        if isinstance(node, _RawJSON):
            token = '@@RAW%d@@' % len(raw)
            raw[token] = str(node)
            return token
        if isinstance(node, dict):
            return {k: swap(v) for k, v in node.items()}
        if isinstance(node, list):
            return [swap(v) for v in node]
        return node

    out = json.dumps(swap(obj), ensure_ascii=False).replace('--', DASH)
    for token, value in raw.items():
        out = out.replace(token, value)
    return out


def _attr_string(attrs):
    if not attrs:
        return ''
    return ' ' + ' '.join(f'{k}="{v}"' for k, v in attrs.items())


def block(seed, tag='div', inner=None, text=None, style=None, classes=None,
          attrs=None, extra=None, name=None, alignfull=False, prefix='', anchor=None):
    """Build one block on the active backend. See `_greenshift_block` for the
    argument reference; both backends take the same call."""
    fn = _core_block if BACKEND == 'core' else _greenshift_block
    return fn(seed, tag=tag, inner=inner, text=text, style=style, classes=classes,
              attrs=attrs, extra=extra, name=name, alignfull=alignfull, prefix=prefix,
              anchor=anchor)


def compile_css(markup):
    """Compile emitted blocks' styleAttributes into one CSS string.

    Pages and posts do not get CSSRender; upstream puts the whole page's CSS into
    the `_gspb_post_css` meta field instead (SKILL.md:259). Normally Greenshift's
    PHP does this compilation; this reproduces its output for element blocks:
    one rule per block for the desktop entry, then one `@media (max-width: ...)`
    rule per further entry at BREAKPOINTS. `null` and `""` entries are skipped,
    the same as the renderer. `customCSS_Extra` is passed through with
    `{CURRENT}` resolved to the block selector.

    Stylemanager blocks contribute their `dynamicGClasses[].css` and `customCss`
    verbatim, so one call covers a page's own classes and its block styles.

    `scripts/probe_responsive.py --parity` diffs this against the live renderer.

    Returns the CSS string. Pass it to WP.set_post_css(page_id, css).
    """
    rules = []
    for m in re.finditer(r'<!-- wp:greenshift-blocks/element (\{.*?\}) -->', markup, re.S):
        try:
            attrs = json.loads(m.group(1).replace(DASH, '--'))
        except ValueError:
            continue
        bid = attrs.get('id')
        # a stylemanager block carries whole CSS strings rather than properties:
        # the class rule (with its media queries) and one string per sub-selector,
        # which is exactly the set the PHP renderer emits for template targets
        for cls in attrs.get('dynamicGClasses') or []:
            if cls.get('css'):
                rules.append(cls['css'])
            for sel in cls.get('selectors') or []:
                if sel.get('css'):
                    rules.append(sel['css'])
        if attrs.get('customCss'):
            rules.append(attrs['customCss'])
        style = attrs.get('styleAttributes')
        if not style or not bid:
            continue
        per_bp = [[] for _ in BREAKPOINTS]
        extra = []
        for prop, value in style.items():
            if prop == 'customCSS_Extra':
                extra.append(str(value).replace('{CURRENT}', '.' + bid))
                continue
            values = value if isinstance(value, list) else [value]
            kebab = re.sub(r'(?<!^)(?=[A-Z])', '-', prop).lower()
            for i, v in enumerate(values[:len(BREAKPOINTS)]):
                if v in (None, ''):
                    continue
                per_bp[i].append('%s:%s' % (kebab, v))
        for i, decls in enumerate(per_bp):
            if not decls:
                continue
            rule = '.%s{%s;}' % (bid, ';'.join(decls))
            rules.append(rule if BREAKPOINTS[i] is None
                         else '@media (max-width:%s){%s}' % (BREAKPOINTS[i], rule))
        rules.extend(extra)
    return ''.join(rules)


def image(seed, src, alt, width, height, style=None, classes=None, prefix='',
          attrs=None, media_id=None):
    """Image block on the active backend. Always lazy, always with intrinsic
    dimensions so the layout does not shift."""
    fn = _core_image if BACKEND == 'core' else _greenshift_image
    return fn(seed, src, alt, width, height, style=style, classes=classes,
              prefix=prefix, attrs=attrs, media_id=media_id)


# --------------------------------------------------------------------------
# Greenshift backend
# --------------------------------------------------------------------------

def _greenshift_block(seed, tag='div', inner=None, text=None, style=None, classes=None,
                      attrs=None, extra=None, name=None, alignfull=False, prefix='',
                      anchor=None):
    """
    Build one Greenshift element block.

    seed       stable string -> deterministic block id
    tag        html tag ('div', 'section', 'h2', 'a', 'button', 'article', ...)
    inner      child block markup (makes this a container: type="inner")
    text       text content (mutually exclusive with inner)
    style      dict of styleAttributes, responsive lists: {"padding": ["40px","24px"]}
               (desktop, tablet, mobile_landscape, mobile_portrait; fewer apply upward)
    classes    extra css classes (stylebook global classes), str or list
    attrs      dict of html attributes; data-*/aria-*/role are auto-declared in JSON
    extra      extra top-level block JSON keys (href, isVariation, formAttributes, ...)
    name       label shown in the editor list view
    """
    block_id = make_id(seed, prefix)
    payload = {'id': block_id}
    if text is not None:
        payload['textContent'] = text
    if tag != 'div':
        payload['tag'] = tag
    # `type` is always explicit. Upstream's converter ends with a literal
    # "always set type explicitly" and never omits it, and its deconverter reads
    # `attrs.type || 'inner'`, so a text block that leaves type out round-trips
    # back as a container and loses its textContent.
    payload['type'] = ('inner' if inner is not None
                       else 'text' if text is not None
                       else 'no')
    payload['localId'] = block_id
    if extra:
        payload.update(extra)
    if alignfull:
        payload['align'] = 'full'

    attrs = dict(attrs or {})
    if 'id' in attrs:
        raise ValueError(
            "block %r passes a raw id attribute. Greenshift renders the HTML id from "
            "the `anchor` key, so a raw id is undeclared markup: Gutenberg flags the "
            "block invalid, offers Attempt recovery, and recovery strips the id. Every "
            "anchor link pointing at it then goes nowhere. Pass anchor='%s' instead."
            % (seed, attrs['id']))
    if anchor:
        payload['anchor'] = anchor
        attrs['id'] = anchor
    # Everything written into the HTML has to be reachable from the JSON, or the
    # block fails validation and recovery strips it. Greenshift renders the
    # attributes below from its own keys; anything else must be declared.
    # `id` is excluded when it came from anchor: Greenshift renders it from that
    # key, so declaring it again would emit the attribute twice
    rendered = _RENDERED_ATTRS | ({'id'} if anchor else frozenset())
    # `type` on a form control goes in formAttributes, never the main JSON and
    # never dynamicAttributes: the spec is explicit about that placement
    if tag in ('button', 'input', 'textarea', 'select'):
        form = dict(payload.get('formAttributes') or {})
        for key in ('type', 'name', 'placeholder', 'required', 'value'):
            if key in attrs:
                form[key] = attrs[key]
                rendered = rendered | {key}
        if form:
            payload['formAttributes'] = form
    declared = [{'name': k, 'value': str(v)} for k, v in attrs.items()
                if k not in rendered]
    if declared:
        existing = payload.get('dynamicAttributes', [])
        payload['dynamicAttributes'] = existing + declared

    if style:
        payload['styleAttributes'] = style
        if TARGET != 'page':
            payload['CSSRender'] = CSSRENDER
    if name:
        payload['metadata'] = {'name': name}

    class_list = [block_id]
    if classes:
        class_list += classes.split() if isinstance(classes, str) else list(classes)
    if alignfull:
        class_list.append('alignfull')
    class_attr = ' '.join(class_list)
    # the spec requires className in the JSON, duplicated in the HTML class
    # attribute; the editor reads the JSON, the front end reads the markup
    payload['className'] = class_attr

    open_tag = f'<{tag} class="{class_attr}"{_attr_string(attrs)}>'
    if text is not None:
        html = f'{open_tag}{text}</{tag}>'
    elif inner is not None:
        html = f'{open_tag}\n{inner}\n</{tag}>'
    else:
        html = f'{open_tag}</{tag}>'

    return f'<!-- wp:greenshift-blocks/element {_encode(payload)} -->\n{html}\n<!-- /wp:greenshift-blocks/element -->\n'


def _greenshift_image(seed, src, alt, width, height, style=None, classes=None,
                      prefix='', attrs=None, media_id=None):
    block_id = make_id(seed, prefix)
    # upstream's converter overrides img's initial 'image' type with 'no'
    payload = {'id': block_id, 'tag': 'img', 'type': 'no', 'localId': block_id,
               'src': src, 'alt': alt,
               'originalWidth': width, 'originalHeight': height}
    declared = [{'name': k, 'value': str(v)} for k, v in (attrs or {}).items()
                if k.startswith(('data-', 'aria-')) or k == 'role']
    if declared:
        payload['dynamicAttributes'] = declared
    if style:
        payload['styleAttributes'] = style
        if TARGET != 'page':
            payload['CSSRender'] = CSSRENDER
    class_attr = block_id + ((' ' + classes) if classes else '')
    return (f'<!-- wp:greenshift-blocks/element {_encode(payload)} -->\n'
            f'<img class="{class_attr}" src="{src}" alt="{alt}" '
            f'width="{width}" height="{height}" loading="lazy"'
            f'{_attr_string(attrs)}/>\n'
            f'<!-- /wp:greenshift-blocks/element -->\n')


# --------------------------------------------------------------------------
# Core backend, native WordPress blocks, no plugin
# --------------------------------------------------------------------------

# wp:group renders any of these via its tagName attribute; anything else has no
# core equivalent and is refused rather than silently wrapped in a div.
_GROUP_TAGS = ('div', 'section', 'article', 'header', 'footer', 'main', 'aside')

# core's style attribute is a fixed schema, not free CSS. This is the slice of it
# that is stable across themes; everything else belongs in a stylebook class.
_STYLE_MAP = {
    'paddingTop': ('spacing', 'padding', 'top'),
    'paddingRight': ('spacing', 'padding', 'right'),
    'paddingBottom': ('spacing', 'padding', 'bottom'),
    'paddingLeft': ('spacing', 'padding', 'left'),
    'marginTop': ('spacing', 'margin', 'top'),
    'marginRight': ('spacing', 'margin', 'right'),
    'marginBottom': ('spacing', 'margin', 'bottom'),
    'marginLeft': ('spacing', 'margin', 'left'),
    'blockGap': ('spacing', 'blockGap'),
    'color': ('color', 'text'),
    'backgroundColor': ('color', 'background'),
    'fontSize': ('typography', 'fontSize'),
    'fontWeight': ('typography', 'fontWeight'),
    'lineHeight': ('typography', 'lineHeight'),
    'textAlign': ('typography', 'textAlign'),
}


def _core_style(style, seed):
    """Translate the supported subset; refuse the rest with somewhere to put it."""
    if not style:
        return None
    out, rejected = {}, []
    for prop, value in style.items():
        path = _STYLE_MAP.get(prop)
        if not path:
            rejected.append(prop)
            continue
        if isinstance(value, list):
            present = [v for v in value if v not in (None, '')]
            if len(present) > 1:
                raise ValueError(
                    'core blocks have no per-block breakpoints, and %r on block %r '
                    'carries %d responsive values. Put the breakpoint in a stylebook '
                    'class (classes=) or collapse it to one fluid value with clamp()/min().'
                    % (prop, seed, len(present)))
            if not present:
                continue
            value = present[0]
        node = out
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    if rejected:
        raise ValueError(
            'core blocks cannot carry arbitrary CSS, and %r asks for %s (on block %r).\n'
            'Core supports only spacing, colour and typography inline. Put these in a '
            'stylebook class and pass classes= instead, which is where breakpoints '
            'already have to live, so the class is probably the right home anyway.'
            % (seed, ', '.join(sorted(rejected)), seed))
    return out or None


def _core_block(seed, tag='div', inner=None, text=None, style=None, classes=None,
                attrs=None, extra=None, name=None, alignfull=False, prefix='',
                anchor=None):
    block_id = make_id(seed, prefix)
    attrs = dict(attrs or {})
    if anchor:
        payload_anchor, attrs['id'] = anchor, anchor
    else:
        payload_anchor = None
    class_list = [block_id] + (
        classes.split() if isinstance(classes, str) else list(classes or []))
    payload = {}
    styles = _core_style(style, seed)
    if styles:
        payload['style'] = styles
    if name:
        payload['metadata'] = {'name': name}
    if alignfull:
        payload['align'] = 'full'
        class_list.append('alignfull')
    if payload_anchor:
        payload['anchor'] = payload_anchor

    body = inner if inner is not None else (text if text is not None else '')
    heading = re.fullmatch(r'h([1-6])', tag)

    if heading:
        payload['level'] = int(heading.group(1))
        block_name = 'heading'
        class_list.insert(0, 'wp-block-heading')
    elif tag == 'p':
        block_name = 'paragraph'
    elif tag in ('ul', 'ol'):
        block_name = 'list'
        if tag == 'ol':
            payload['ordered'] = True
    elif tag == 'li':
        block_name = 'list-item'
    elif tag in _GROUP_TAGS:
        block_name = 'group'
        if tag != 'div':
            payload['tagName'] = tag
        payload.setdefault('layout', {'type': 'constrained'})
    else:
        raise ValueError(
            'no core block renders <%s> (block %r).\n'
            'Core covers %s via wp:group, h1-h6, p, ul/ol/li and img. For a link or '
            'CTA use button(); for a link inside prose, put the <a> in the text of a '
            'paragraph rather than making it its own block. If this genuinely needs a '
            'custom element, staying on the greenshift backend is the better answer.'
            % (tag, seed, '/'.join(_GROUP_TAGS)))

    class_list = [c for c in dict.fromkeys(class_list) if c]
    payload['className'] = ' '.join(c for c in class_list if c != 'wp-block-heading')
    if extra:
        payload.update(extra)

    attr_json = (' ' + _encode(payload)) if payload else ''
    open_tag = '<%s class="%s"%s>' % (tag, ' '.join(class_list), _attr_string(attrs))
    sep = '\n' if inner is not None else ''
    html = '%s%s%s%s</%s>' % (open_tag, sep, body, sep, tag)
    return '<!-- wp:%s%s -->\n%s\n<!-- /wp:%s -->\n' % (
        block_name, attr_json, html, block_name)


def _core_image(seed, src, alt, width, height, style=None, classes=None,
                prefix='', attrs=None, media_id=None):
    block_id = make_id(seed, prefix)
    class_list = [block_id] + (
        classes.split() if isinstance(classes, str) else list(classes or []))
    payload = {'sizeSlug': 'full'}
    # core resolves srcset and responsive sizes from the attachment id, so pass it
    # whenever the media map has one, without it WordPress serves the bare src
    if media_id:
        payload['id'] = int(media_id)
    styles = _core_style(style, seed)
    if styles:
        payload['style'] = styles
    payload['className'] = ' '.join(dict.fromkeys(class_list))
    return ('<!-- wp:image %s -->\n'
            '<figure class="wp-block-image size-full %s">'
            '<img src="%s" alt="%s" width="%s" height="%s" loading="lazy"%s/>'
            '</figure>\n'
            '<!-- /wp:image -->\n'
            % (_encode(payload), ' '.join(dict.fromkeys(class_list)),
               src, alt, width, height, _attr_string(attrs)))


def svg_icon(seed, path, viewbox='0 0 512 512', size='18px', fill='currentColor', prefix=''):
    """Inline SVG block. Decorative by default (aria-hidden), label the parent link.

    Carries the `icon` object the format specifies for `tag:"svg"`, with the markup
    unicode-escaped as required (see reference/upstream-block-spec.md). Emitting the
    raw <svg> alone renders, but leaves the block without the attribute the editor
    reads, so a re-save in Gutenberg can lose the graphic.
    """
    if BACKEND == 'core':
        raise ValueError(
            'svg_icon() emits a raw <svg>, which no core block renders (block %r). On '
            'the core backend put the icon on a stylebook class as a mask-image, or '
            'upload it and use image().' % seed)
    block_id = make_id(seed, prefix)
    svg = '<svg viewBox="%s"><path d="%s"/></svg>' % (viewbox, path)
    escaped = (svg.replace('<', '\\u003c').replace('>', '\\u003e')
                  .replace('"', '\\u0022'))
    payload = {'id': block_id, 'tag': 'svg', 'type': 'no', 'localId': block_id,
               'icon': {'icon': {'svg': _RawJSON(escaped), 'image': ''},
                        'fill': fill, 'fillhover': fill, 'type': 'svg'},
               'dynamicAttributes': [{'name': 'aria-hidden', 'value': 'true'}],
               'styleAttributes': {'width': [size], 'height': [size], 'fill': [fill]}}
    if TARGET != 'page':
        payload['CSSRender'] = CSSRENDER
    return (f'<!-- wp:greenshift-blocks/element {_encode(payload)} -->\n'
            f'<svg viewBox="{viewbox}" class="{block_id}" aria-hidden="true">'
            f'<path d="{path}" /></svg>\n'
            f'<!-- /wp:greenshift-blocks/element -->\n')


# A core/html block is opaque: its contents cannot be edited in the block editor,
# do not pick up stylebook classes or tokens, and are skipped by every check in
# this skill. That is right for a script, a stylesheet or a shortcode, and wrong
# for anything a person will want to edit later. These patterns tell them apart.
_EXEMPT = re.compile(r'<(script|style|template|noscript)\b|^\s*\[[a-z][\w-]*[\s\]]', re.I)
_STRUCTURAL = re.compile(r'<(h[1-6]|article|img|figure|table)\b', re.I)
_BLOCK_LEVEL = re.compile(r'<(div|p|ul|ol|li|h[1-6]|article|section|figure|img|table)\b', re.I)


def raw_html(content, reason=None):
    """Wrap a script, stylesheet or shortcode in a core/html block.

    Not for page content. Markup buried in core/html cannot be edited in the block
    editor, ignores the stylebook (so it drifts the moment a token or a layout class
    changes), and is invisible to the accessibility and block checks. Build content
    from element blocks instead: block(), grid(), heading(), image(), section().

    Raises on content-shaped input. For markup that genuinely has to stay raw - a
    third-party embed, an SVG sprite - pass reason= to say why.
    """
    if reason is None and not _EXEMPT.search(content):
        if _STRUCTURAL.search(content) or len(_BLOCK_LEVEL.findall(content)) >= 3:
            raise ValueError(
                'raw_html() was handed page content, not a script or shortcode.\n'
                '  ' + content.strip()[:120] + '...\n'
                'Content in a core/html block is uneditable in the block editor, '
                'ignores the stylebook, and is skipped by the checks. Rebuild it with '
                'element blocks - block()/grid()/heading()/image()/section(). If the '
                'raw markup is genuinely required, pass reason="...".')
    return f'<!-- wp:html -->\n{content}\n<!-- /wp:html -->\n'


def shortcode(code):
    """Embed a shortcode, e.g. shortcode('[gravityform id="3" title="false" ajax="true"]')."""
    return raw_html(code, reason='shortcode')


def gravity_form(form_id, title=False, description=False, ajax=True):
    """Embed a Gravity Forms form as its own block, which the editor renders and
    the client can reconfigure, rather than as an opaque shortcode."""
    attrs = {'formId': str(form_id), 'title': bool(title), 'description': bool(description),
             'ajax': bool(ajax)}
    return '<!-- wp:gravityforms/form %s /-->\n' % json.dumps(attrs, separators=(',', ':'))


# --------------------------------------------------------------------------
# Layout helpers, these assume the stylebook classes from reference/starter-tokens.json
# --------------------------------------------------------------------------

def section(seed, inner, bg=None, bg_image=None, pad='var(--gt-section-pad, clamp(3rem, 7vw, 5rem))',
            tag='section', name=None, prefix=''):
    """Full-bleed section wrapper with fluid vertical padding.

    On the core backend the layout comes from the `gt-section` stylebook class
    rather than inline CSS, because core blocks cannot carry arbitrary properties.
    The class ships in reference/starter-tokens.json and holds the same rules.
    """
    if BACKEND == 'core':
        style = {'paddingTop': [pad], 'paddingBottom': [pad]}
        if bg:
            style['backgroundColor'] = [bg]
        if bg_image:                      # no inline background-image on core blocks
            raise ValueError(
                'a background image on block %r needs a stylebook class on the core '
                'backend. Core blocks carry no background-image property. Add one '
                'with the url baked in, or stay on the greenshift backend.' % seed)
        return block(seed, tag, inner=inner, style=style, classes='gt-section',
                     name=name, alignfull=True, prefix=prefix)

    # The documented full-width shell: `wp-section alignfull` carrying
    # data-type="section-component", with the side padding and margins coming
    # from the theme's own variables. Keep the alignfull class, the wide-size
    # variable and the spacing-side variable; padding top/bottom is yours to set.
    style = {
        'display': ['flex'], 'justifyContent': ['center'], 'flexDirection': ['column'],
        'alignItems': ['center'],
        'paddingLeft': ['var(--wp--spacing--side, min(3vw, 20px))'],
        'paddingRight': ['var(--wp--spacing--side, min(3vw, 20px))'],
        'paddingTop': [pad], 'paddingBottom': [pad],
        'marginTop': ['0px'], 'marginBottom': ['0px'], 'position': ['relative'],
    }
    if bg:
        style['backgroundColor'] = [bg]
    if bg_image:
        style['backgroundImage'] = [f'url({bg_image})']
        style['backgroundSize'] = ['cover']
        style['backgroundPosition'] = ['center center']
    return block(seed, tag, inner=inner, style=style, classes='wp-section',
                 attrs={'data-type': 'section-component'},
                 extra={'isVariation': 'contentwrapper'}, name=name,
                 alignfull=True, prefix=prefix)


def local_classes(classes):
    """Normalise local-class input to the shape upstream's converter emits.

    Accepts a dict {name: css}, or a list of dicts carrying `value` (or `id`)
    and `css`. Entries that already carry `type` are taken as complete. The
    converter's shape is used rather than the two-key example in
    validate-styles.md because it is what `deconvert.js` reads back and what
    the editor's class manager displays; the short shape renders but does not
    round-trip.
    """
    if not classes:
        return []
    items = ([{'value': k, 'css': v} for k, v in classes.items()]
             if isinstance(classes, dict) else list(classes))
    out = []
    for item in items:
        if 'type' in item and 'value' in item:
            out.append(item)
            continue
        name = item.get('value') or item.get('id')
        css = item.get('css', '')
        if not name:
            raise ValueError('local class without a name: %r' % (item,))
        mentioned = css + ''.join(s.get('css', '') for s in item.get('selectors') or [])
        if ('.' + name) not in mentioned:
            raise ValueError(
                "local class %r has CSS that never mentions .%s; the renderer emits "
                "the css string verbatim, so this rule would style nothing." % (name, name))
        out.append({'value': name, 'type': 'local', 'label': item.get('label', name),
                    'localed': False, 'css': css,
                    'attributes': {'styleAttributes': item.get('styleAttributes') or {}},
                    'originalBlock': 'greenshift-blocks/element',
                    'selectors': item.get('selectors') or []})
    return out


def style_manager(seed, classes=None, custom_css=None, custom_js=None, name=None,
                  prefix=''):
    """A stylemanager block: one page's own classes and CSS, carried in the block tree.

    This is how upstream's converter ships CSS that belongs to one page rather
    than to the site: an empty block with `isVariation: "stylemanager"` holding
    `dynamicGClasses`, instead of pushing every class into the global stylebook.
    The split is by scope, not by mechanism:

        site-wide tokens and shared layout   stylebook (global_settings)
        this page's own classes              style_manager(...)
        compiled block styles on a page      _gspb_post_css via compile_css()

    One stylemanager per page, first in the content. Reference its classes from
    ordinary blocks with classes=. On a template target it carries CSSRender like
    any styled block; on a page target compile_css() folds its CSS into the page
    stylesheet.

    classes     {'home-hero': '.home-hero{...}', ...} or a list, see local_classes()
    custom_css  CSS that belongs to no class (tag, body, keyframes); `customCss`.
                Page targets only: compile_css() folds it into the page CSS. The
                PHP renderer behind CSSRender emits dynamicGClasses[].css and
                selectors[].css and nothing else, so on a template target
                customCss (and customCSS_Extra anywhere) is editor-only. Verified
                by probe_responsive.py; a template part's class-less CSS belongs
                in the stylebook, which is site-wide like the part itself.
    custom_js   script for this page, event-delegated on document
    """
    bid = make_id(seed, prefix)
    local = local_classes(classes)
    if custom_css and TARGET != 'page':
        raise ValueError(
            'style_manager(custom_css=...) on a template target: the PHP renderer '
            'ignores customCss, so this CSS would never reach the page. Put it in a '
            'stylebook class (a template part is site-wide anyway) or, if it must '
            'travel with the part, inside a local class string: '
            "classes={'part-css': '.part-css{} " + custom_css[:40].replace("'", '"') + "...'}")
    payload = {'id': bid, 'tag': 'div', 'type': 'no', 'localId': bid,
               'isVariation': 'stylemanager'}
    if local:
        payload['dynamicGClasses'] = local
    if custom_css:
        payload['customCss'] = custom_css
    if custom_js:
        payload['customJs'] = custom_js
        payload['customJsEnabled'] = True
    if name:
        payload['metadata'] = {'name': name}
    # CSSRender applies to template targets only, same rule as any other block
    if TARGET != 'page' and (local or custom_css):
        payload['CSSRender'] = CSSRENDER
    # the carrier div lists every local class, which is how the editor's class
    # manager finds them and how deconvert.js reads them back
    names = ' '.join(c['value'] for c in local)
    if names:
        payload['className'] = names
    class_attr = ' class="%s"' % names if names else ''
    open_c = '<!-- wp:greenshift-blocks/element ' + _encode(payload) + ' -->'
    return open_c + '\n<div%s></div>\n' % class_attr + '<!-- /wp:greenshift-blocks/element -->\n'


# Libraries the Greenshift plugin ships, relative to its folder. Verified on
# gl-page-builder 3.3.7: GSAP 3.12.2 and its plugins are classic UMD files
# (global `gsap`, `ScrollTrigger`, ...), Motion 12 is an ES module. Upstream's
# `import gsap from '{{PLUGIN_URL}}/libs/motion/gsap.js'` matches neither the
# path nor the format on this build: that file does not exist, and importing the
# UMD file as a module throws. Load GSAP with a classic script tag.
GSAP_CORE = 'libs/gsap/gsap.min.js'
GSAP_PLUGINS = {
    'ScrollTrigger': 'libs/gsap/ScrollTrigger.min.js',
    'ScrollToPlugin': 'libs/gsap/ScrollToPlugin.min.js',
    'Flip': 'libs/gsap/Flip.min.js',
    'SplitText': 'libs/gsap/SplitText.min.js',
    'TextPlugin': 'libs/gsap/TextPlugin.min.js',
    'Observer': 'libs/gsap/Observer.min.js',
}
MOTION_MODULE = 'libs/motion/motion.js'

REDUCED_MOTION_GUARD = (
    "if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { return; }")


def script_block(js, module=False, srcs=(), respect_reduced_motion=True):
    """A `wp:html` block carrying a page script (upstream's option C).

    Raw `wp:html` output runs as-is, so the script needs no `gspb_block_js`
    entry and no block id. Put it last in the page content: by then every
    element it addresses is in the DOM. The body is wrapped so an early return
    honours `prefers-reduced-motion`; pass respect_reduced_motion=False for
    scripts that are not motion (a filter, a menu toggle).

    js       script body. In module mode it may use `import`.
    module   emit type="module" (needed for `import`, e.g. Motion)
    srcs     classic <script src> tags emitted first (e.g. GSAP and its plugins)
    """
    tags = ''.join('<script src="%s"></script>\n' % s for s in srcs)
    if respect_reduced_motion and not module:
        body = '(function(){\n%s\n%s\n})();' % (REDUCED_MOTION_GUARD, js)
    elif respect_reduced_motion:
        body = "if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {\n%s\n}" % js
    else:
        body = js
    kind = ' type="module"' if module else ''
    return ('<!-- wp:html -->\n%s<script%s data-wp-block-html="js">\n%s\n</script>\n'
            '<!-- /wp:html -->\n' % (tags, kind, body))


def gsap_script(js, plugin_url, plugins=('ScrollTrigger',)):
    """GSAP page script: loads the plugin's bundled GSAP and the named GSAP
    plugins with classic script tags, registers them, then runs `js` with the
    globals `gsap`, `ScrollTrigger` and so on available.

    plugin_url  from WP.greenshift_plugin_url(); never guess it
    plugins     names from GSAP_PLUGINS
    """
    unknown = [p for p in plugins if p not in GSAP_PLUGINS]
    if unknown:
        raise ValueError('unknown GSAP plugins %s; bundled: %s' % (unknown, sorted(GSAP_PLUGINS)))
    srcs = [plugin_url.rstrip('/') + '/' + GSAP_CORE] + \
           [plugin_url.rstrip('/') + '/' + GSAP_PLUGINS[p] for p in plugins]
    register = ('gsap.registerPlugin(%s);\n' % ', '.join(plugins)) if plugins else ''
    return script_block(register + js, srcs=srcs)


def motion_script(js, plugin_url, names=('animate', 'inView', 'scroll', 'stagger')):
    """Motion page script (ES module): imports the named functions from the
    plugin's bundled `motion.js`, then runs `js`."""
    src = plugin_url.rstrip('/') + '/' + MOTION_MODULE
    return script_block('import { %s } from "%s";\n%s' % (', '.join(names), src, js), module=True)


def has_greenshift_blocks(markup):
    """True when markup carries Greenshift element blocks, which is how to tell a
    Greenlight header (patch surgically) from another theme's (rewrite freely)."""
    return 'wp:greenshift-blocks/' in (markup or '')


def container(seed, inner, width='1290px', name=None, prefix=''):
    """Centered content column inside a section."""
    if BACKEND == 'core':
        # gt-container carries the max-width and centring; core's constrained
        # layout handles the rest
        return block(seed, 'div', inner=inner, name=name, prefix=prefix,
                     classes='gt-container')
    # documented inner wrapper: width from the theme's wide-size variable
    return block(seed, 'div', inner=inner, name=name, prefix=prefix,
                 classes='wp-content-wrap',
                 attrs={'data-type': 'content-area-component'},
                 style={'maxWidth': ['100%'],
                        'width': ['var(--wp--style--global--wide-size, %s)' % width],
                        'display': ['flex'], 'flexDirection': ['column'],
                        'alignItems': ['center']})


def grid(seed, inner, variant='gt-grid-4', style=None, name=None, prefix=''):
    """
    Responsive grid on a shared stylebook class. The class carries the breakpoints
    because the layout is shared across pages, not because responsive arrays are
    unsafe; a one-off grid can pass style={'gridTemplateColumns': [...]} directly.
    variant: gt-grid-2 | gt-grid-3 | gt-grid-4 | gt-grid-even | gt-grid-split
    """
    return block(seed, 'div', inner=inner, classes=variant, style=style,
                 name=name, prefix=prefix)


def button(seed, text, href, variant='primary', new_tab=False, prefix=''):
    """Link styled as a button via stylebook classes.

    Core has no element block, so a link cannot be a bare block there; it uses the
    native wp:buttons / wp:button pair, which renders the same anchor and keeps the
    stylebook class.
    """
    cls = 'gt-btn-primary' if variant == 'primary' else 'gt-btn-outline'
    if BACKEND == 'core':
        block_id = make_id(seed, prefix)
        rel = ' rel="noopener"' if new_tab else ''
        target = ' target="_blank"' if new_tab else ''
        inner = ('<!-- wp:button {"className":"%s %s"} -->\n'
                 '<div class="wp-block-button %s %s">'
                 '<a class="wp-block-button__link wp-element-button" href="%s"%s%s>%s</a>'
                 '</div>\n<!-- /wp:button -->' % (block_id, cls, block_id, cls,
                                                  href, target, rel, text))
        return ('<!-- wp:buttons -->\n<div class="wp-block-buttons">\n%s\n</div>\n'
                '<!-- /wp:buttons -->\n' % inner)

    attrs = {'href': href}
    extra = {'href': href}
    if new_tab:
        attrs['target'] = '_blank'
        attrs['rel'] = 'noopener'
        extra['linkNewWindow'] = True
    return block(seed, 'a', text=text, attrs=attrs, extra=extra, prefix=prefix,
                 classes=cls)


def heading(seed, level, text, margin_bottom='1rem', align=None, prefix=''):
    """
    Heading with minimal styling, size/weight/colour come from stylebook element styles.
    Keep one h1 per page; use h2 for sections and h3 for cards.
    """
    style = {'marginTop': ['0px'], 'marginBottom': [margin_bottom]}
    if align:
        style['textAlign'] = [align]
    return block(seed, f'h{level}', text=text, style=style, prefix=prefix)


def eyebrow(seed, text, tone='', prefix=''):
    """Small uppercase label above a heading. A div, never a heading. It is not structure."""
    suffix = f'-{tone}' if tone else ''
    return block(seed, 'div', text=text, classes=f'gt-eyebrow{suffix}',
                 name='Eyebrow', prefix=prefix)


def page_wrapper(seed, inner, bg='var(--gt-cream, #fbf6ec)', prefix=''):
    """Outermost full-width wrapper for a generated page."""
    if BACKEND == 'core':
        return block(seed, 'div', inner=inner, alignfull=True, name='Page Wrapper',
                     prefix=prefix, style={'backgroundColor': [bg]})
    return block(seed, 'div', inner=inner, alignfull=True, name='Page Wrapper', prefix=prefix,
                 style={'marginBlockStart': ['0px'], 'backgroundColor': [bg]})


def svg_icon_or_skip(seed, *args, **kwargs):
    """svg_icon has no core equivalent; on that backend an icon belongs in CSS
    (mask-image on a stylebook class) or as an uploaded SVG via image()."""
    if BACKEND == 'core':
        raise ValueError(
            'svg_icon() emits a raw <svg> element, which no core block renders '
            '(block %r). On the core backend put the icon on a stylebook class as a '
            'mask-image, or upload it and use image().' % seed)
    return svg_icon(seed, *args, **kwargs)
