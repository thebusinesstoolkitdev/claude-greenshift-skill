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

1. CSSRender. Every block carrying styleAttributes gets `"CSSRender": true` so the
   SERVER compiles its CSS. REST-pushed blocks never get editor-compiled CSS, so
   without this they render completely unstyled.
2. Escaped dashes. HTML comments cannot contain `--`, so CSS custom properties are
   escaped to \\u002d\\u002d inside the block JSON.
3. Declared attributes, any data-*/aria-*/role attribute must appear BOTH in the
   block JSON (`dynamicAttributes`) and in the HTML. Raw-only attributes fail block
   validation, Gutenberg offers "Attempt recovery", and recovery strips them.

Also: keep styleAttributes SINGLE-VALUE (use clamp()/min()). The format is a
four-value responsive array, ["desktop","tablet","mobile_landscape","mobile_portrait"],
fewer values applying upward, but multi-value arrays pushed over REST were observed
dropping the smallest entry, so mobile inherited desktop. Put breakpoint logic in
stylebook classes instead.

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
    style      dict of styleAttributes, SINGLE-VALUE lists: {"marginTop": ["0px"]}
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
    declared = [{'name': k, 'value': str(v)} for k, v in attrs.items()
                if k not in rendered]
    if declared:
        existing = payload.get('dynamicAttributes', [])
        payload['dynamicAttributes'] = existing + declared

    if style:
        payload['styleAttributes'] = style
        payload['CSSRender'] = True
    if name:
        payload['metadata'] = {'name': name}

    class_list = [block_id]
    if classes:
        class_list += classes.split() if isinstance(classes, str) else list(classes)
    if alignfull:
        class_list.append('alignfull')
    class_attr = ' '.join(class_list)

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
        payload['CSSRender'] = True
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
        if isinstance(value, list):          # single-value lists, per the house rule
            value = value[0]
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
               'styleAttributes': {'width': [size], 'height': [size], 'fill': [fill]},
               'CSSRender': True}
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
    """Embed a shortcode, e.g. shortcode('[fluentform id="3"]')."""
    return raw_html(code, reason='shortcode')


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

    style = {
        'display': ['flex'], 'justifyContent': ['center'], 'flexDirection': ['column'],
        'alignItems': ['center'],
        'paddingLeft': ['min(3vw, 20px)'], 'paddingRight': ['min(3vw, 20px)'],
        'paddingTop': [pad], 'paddingBottom': [pad], 'marginBlockStart': ['0px'],
    }
    if bg:
        style['backgroundColor'] = [bg]
    if bg_image:
        style['backgroundImage'] = [f'url({bg_image})']
        style['backgroundSize'] = ['cover']
        style['backgroundPosition'] = ['center center']
    return block(seed, tag, inner=inner, style=style,
                 extra={'isVariation': 'contentwrapper'}, name=name,
                 alignfull=True, prefix=prefix)


def container(seed, inner, width='1290px', name=None, prefix=''):
    """Centered content column inside a section."""
    if BACKEND == 'core':
        # gt-container carries the max-width and centring; core's constrained
        # layout handles the rest
        return block(seed, 'div', inner=inner, name=name, prefix=prefix,
                     classes='gt-container')
    return block(seed, 'div', inner=inner, name=name, prefix=prefix,
                 style={'maxWidth': ['100%'], 'width': [width], 'display': ['flex'],
                        'flexDirection': ['column'], 'alignItems': ['center']})


def grid(seed, inner, variant='gt-grid-4', style=None, name=None, prefix=''):
    """
    Responsive grid. Breakpoints live in the stylebook class, NOT in styleAttributes.
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
