# -*- coding: utf-8 -*-
"""
Greenshift block markup builder.

Emits `wp:greenshift-blocks/element` block comments + matching HTML that survive
Gutenberg validation and render correctly when pushed over the REST API.

Three rules are baked in and you should not work around them:

1. CSSRender — every block carrying styleAttributes gets `"CSSRender": true` so the
   SERVER compiles its CSS. REST-pushed blocks never get editor-compiled CSS, so
   without this they render completely unstyled.
2. Escaped dashes — HTML comments cannot contain `--`, so CSS custom properties are
   escaped to \\u002d\\u002d inside the block JSON.
3. Declared attributes — any data-*/aria-*/role attribute must appear BOTH in the
   block JSON (`dynamicAttributes`) and in the HTML. Raw-only attributes fail block
   validation, Gutenberg offers "Attempt recovery", and recovery strips them.

Also: keep styleAttributes SINGLE-VALUE (use clamp()/min()). Greenshift's server-side
CSSRender mishandles 3-entry responsive arrays — the mobile entry is dropped and mobile
falls back to the desktop value. Put breakpoint logic in stylebook classes instead.
"""
import hashlib
import json

DASH = '\\u002d\\u002d'  # escaped `--` for use inside block-comment JSON

_used_ids = set()
_id_cache = {}


def gsid(seed, prefix=''):
    """Deterministic 7-char Greenshift block id from a seed string."""
    key = prefix + seed
    if key in _id_cache:
        return _id_cache[key]
    digest = hashlib.md5(key.encode()).hexdigest()
    for i in range(25):
        candidate = 'gsbp-' + digest[i:i + 7]
        if candidate not in _used_ids:
            _used_ids.add(candidate)
            _id_cache[key] = candidate
            return candidate
    raise RuntimeError('could not allocate unique block id for ' + seed)


def _encode(obj):
    return json.dumps(obj, ensure_ascii=False).replace('--', DASH)


def _attr_string(attrs):
    if not attrs:
        return ''
    return ' ' + ' '.join(f'{k}="{v}"' for k, v in attrs.items())


def block(seed, tag='div', inner=None, text=None, style=None, classes=None,
          attrs=None, extra=None, name=None, alignfull=False, prefix=''):
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
    block_id = gsid(seed, prefix)
    payload = {'id': block_id}
    if text is not None:
        payload['textContent'] = text
    if tag != 'div':
        payload['tag'] = tag
    if inner is not None:
        payload['type'] = 'inner'
    payload['localId'] = block_id
    if extra:
        payload.update(extra)
    if alignfull:
        payload['align'] = 'full'

    attrs = dict(attrs or {})
    declared = [{'name': k, 'value': str(v)} for k, v in attrs.items()
                if k.startswith(('data-', 'aria-')) or k == 'role']
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


def image(seed, src, alt, width, height, style=None, classes=None, prefix=''):
    """Image block. Always lazy-loaded, always with intrinsic dimensions (CLS)."""
    block_id = gsid(seed, prefix)
    payload = {'id': block_id, 'tag': 'img', 'localId': block_id, 'src': src, 'alt': alt,
               'originalWidth': width, 'originalHeight': height}
    if style:
        payload['styleAttributes'] = style
        payload['CSSRender'] = True
    class_attr = block_id + ((' ' + classes) if classes else '')
    return (f'<!-- wp:greenshift-blocks/element {_encode(payload)} -->\n'
            f'<img class="{class_attr}" src="{src}" alt="{alt}" '
            f'width="{width}" height="{height}" loading="lazy"/>\n'
            f'<!-- /wp:greenshift-blocks/element -->\n')


def svg_icon(seed, path, viewbox='0 0 512 512', size='18px', fill='currentColor', prefix=''):
    """Inline SVG block. Decorative by default (aria-hidden) — label the parent link."""
    block_id = gsid(seed, prefix)
    payload = {'id': block_id, 'tag': 'svg', 'localId': block_id,
               'dynamicAttributes': [{'name': 'aria-hidden', 'value': 'true'}],
               'styleAttributes': {'width': [size], 'height': [size], 'fill': [fill]},
               'CSSRender': True}
    return (f'<!-- wp:greenshift-blocks/element {_encode(payload)} -->\n'
            f'<svg viewBox="{viewbox}" class="{block_id}" aria-hidden="true">'
            f'<path d="{path}" /></svg>\n'
            f'<!-- /wp:greenshift-blocks/element -->\n')


def raw_html(content):
    """Wrap arbitrary HTML (forms, shortcodes, scripts) in a core/html block."""
    return f'<!-- wp:html -->\n{content}\n<!-- /wp:html -->\n'


def shortcode(code):
    """Embed a shortcode, e.g. shortcode('[fluentform id=\"3\"]')."""
    return raw_html(code)


# --------------------------------------------------------------------------
# Layout helpers — these assume the stylebook classes from reference/starter-tokens.json
# --------------------------------------------------------------------------

def section(seed, inner, bg=None, bg_image=None, pad='var(--gt-section-pad, clamp(3rem, 7vw, 5rem))',
            tag='section', name=None, prefix=''):
    """Full-bleed section wrapper with fluid vertical padding."""
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
    """Link styled as a button via stylebook classes."""
    attrs = {'href': href}
    extra = {'href': href}
    if new_tab:
        attrs['target'] = '_blank'
        attrs['rel'] = 'noopener'
        extra['linkNewWindow'] = True
    return block(seed, 'a', text=text, attrs=attrs, extra=extra, prefix=prefix,
                 classes='gt-btn-primary' if variant == 'primary' else 'gt-btn-outline')


def heading(seed, level, text, margin_bottom='1rem', align=None, prefix=''):
    """
    Heading with minimal styling — size/weight/colour come from stylebook element styles.
    Keep one h1 per page; use h2 for sections and h3 for cards.
    """
    style = {'marginTop': ['0px'], 'marginBottom': [margin_bottom]}
    if align:
        style['textAlign'] = [align]
    return block(seed, f'h{level}', text=text, style=style, prefix=prefix)


def eyebrow(seed, text, tone='', prefix=''):
    """Small uppercase label above a heading. A div, never a heading — it is not structure."""
    suffix = f'-{tone}' if tone else ''
    return block(seed, 'div', text=text, classes=f'gt-eyebrow{suffix}',
                 name='Eyebrow', prefix=prefix)


def page_wrapper(seed, inner, bg='var(--gt-cream, #fbf6ec)', prefix=''):
    """Outermost full-width wrapper for a generated page."""
    return block(seed, 'div', inner=inner, alignfull=True, name='Page Wrapper', prefix=prefix,
                 style={'marginBlockStart': ['0px'], 'backgroundColor': [bg]})
