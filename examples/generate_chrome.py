# -*- coding: utf-8 -*-
# EXAMPLE — a real four-page build, with the client details swapped out.
# Copy into your project and adapt. The reusable primitives live in
# scripts/gsblocks.py; this file shows how a whole page is assembled.
"""Build header (surgical edit) + footer (rewrite) template parts."""
import json, hashlib, re, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

U = "https://example.com/wp-content/uploads/2025/01"
D = "\\u002d\\u002d"

_used = set()
_ids = {}
def sid(seed):
    if seed not in _ids:
        h = hashlib.md5(('chrome' + seed).encode()).hexdigest()
        for i in range(0, 25):
            c = 'gsbp-' + h[i:i+7]
            if c not in _used:
                _used.add(c)
                _ids[seed] = c
                break
    return _ids[seed]

def block(seed, tag, inner=None, text=None, style=None, extra=None, html_attrs='', gclass='', name=None, alignfull=False, classname=None):
    i = sid(seed)
    j = {"id": i}
    if text is not None:
        j["textContent"] = text
    if tag != 'div':
        j["tag"] = tag
    if inner is not None:
        j["type"] = "inner"
    if classname:
        j["className"] = classname
    j["localId"] = i
    if extra:
        j.update(extra)
    if alignfull:
        j["align"] = "full"
    if style:
        j["styleAttributes"] = style
        j["CSSRender"] = True
    if name:
        j["metadata"] = {"name": name}
    js = json.dumps(j, ensure_ascii=False).replace('--', D)
    cls_parts = []
    if classname:
        cls_parts.append(classname)
    cls_parts.append(i)
    if gclass:
        cls_parts.append(gclass)
    if alignfull:
        cls_parts.append('alignfull')
    cls = ' '.join(cls_parts)
    attrs = (' ' + html_attrs) if html_attrs else ''
    if text is not None:
        h = f'<{tag} class="{cls}"{attrs}>{text}</{tag}>'
    elif inner is not None:
        h = f'<{tag} class="{cls}"{attrs}>\n{inner}\n</{tag}>'
    else:
        h = f'<{tag} class="{cls}"{attrs}></{tag}>'
    return f'<!-- wp:greenshift-blocks/element {js} -->\n{h}\n<!-- /wp:greenshift-blocks/element -->\n'

# ---------- 1. Topbar ----------
topbar = block('topbar', 'div', inner=
    block('topbartxt', 'div', text='Come visit us in-store · Made &amp; styled with care in Ashford, Kent',
          gclass='gt-topbar-text'),
    style={"backgroundColor": ["var(--gt-olive-deep, #5a663c)"], "paddingTop": ["10px"], "paddingBottom": ["10px"],
           "paddingLeft": ["min(3vw, 20px)"], "paddingRight": ["min(3vw, 20px)"], "marginBlockStart": ["0px"]},
    name='Topbar', alignfull=True)

# ---------- 2. Menu items ----------
def menu_item(seed, label, href):
    link = block(seed + 'a', 'a', text=label, classname='gs-top-level-item',
                 extra={"href": href, "isVariation": "menu_item_link"}, html_attrs=f'href="{href}"')
    return ('<!-- wp:greenshift-blocks/element {"id":"%s","tag":"li","type":"inner","localId":"%s","isVariation":"menu_item","metadata":{"name":"Menu Item"}} -->\n'
            '<li>%s</li>\n'
            '<!-- /wp:greenshift-blocks/element -->\n') % (sid(seed), sid(seed), link.rstrip('\n'))

menu_items = (menu_item('mi-home', 'Home', '/') +
              menu_item('mi-coll', 'Collection', '/collection/') +
              menu_item('mi-about', 'About', '/about/') +
              menu_item('mi-contact', 'Contact', '/contact/'))

# ---------- 3. Header icons (search + heart) ----------
SEARCH_PATH = 'M416 208c0 45.9-14.9 88.3-40 122.7l126.6 126.7c12.5 12.5 12.5 32.8 0 45.3s-32.8 12.5-45.3 0L330.7 376c-34.4 25.2-76.8 40-122.7 40C93.1 416 0 322.9 0 208S93.1 0 208 0S416 93.1 416 208zM208 352a144 144 0 1 0 0-288 144 144 0 1 0 0 288z'
HEART_PATH = 'M47.6 300.4L228.3 469.1c7.5 7 17.4 10.9 27.7 10.9s20.2-3.9 27.7-10.9L464.4 300.4c30.4-28.3 47.6-68 47.6-109.5v-5.8c0-69.9-50.5-129.5-119.4-141C347 36.5 300.6 51.4 268 84L256 96 244 84c-32.6-32.6-79-47.5-124.6-39.9C50.5 55.6 0 115.2 0 185.1v5.8c0 41.5 17.2 81.2 47.6 109.5z'

def icon_link(seed, path, label, href, vb):
    i = sid(seed)
    svg_i = sid(seed + 'svg')
    svg_json = json.dumps({"id": svg_i, "tag": "svg", "localId": svg_i,
        "dynamicAttributes": [{"name": "aria-hidden", "value": "true"}],
        "styleAttributes": {"width": ["18px"], "height": ["18px"], "fill": ["currentColor"]}, "CSSRender": True}).replace('--', D)
    svg = (f'<!-- wp:greenshift-blocks/element {svg_json} -->\n'
           f'<svg viewBox="{vb}" width="18" height="18" class="{svg_i}" aria-hidden="true"><path d="{path}" /></svg>\n'
           f'<!-- /wp:greenshift-blocks/element -->')
    j = json.dumps({"id": i, "tag": "a", "type": "inner", "localId": i, "href": href,
        "dynamicAttributes": [{"name": "aria-label", "value": label}],
        "styleAttributes": {"display": ["inline-flex"], "alignItems": ["center"], "justifyContent": ["center"],
            "width": ["36px"], "height": ["36px"], "borderRadius": ["50%"], "color": ["var(--gt-ink, #33291f)"],
            "transition": ["all 0.25s ease"], "color_hover": ["var(--gt-purple, #7e5aa6)"],
            "backgroundColor_hover": ["rgba(126,90,166,0.08)"]},
        "CSSRender": True, "metadata": {"name": label}}, ensure_ascii=False).replace('--', D)
    return (f'<!-- wp:greenshift-blocks/element {j} -->\n'
            f'<a class="{i}" href="{href}" aria-label="{label}">\n{svg}\n</a>\n'
            f'<!-- /wp:greenshift-blocks/element -->\n')

icons = block('hdricons', 'div', inner=
    icon_link('ic-search', SEARCH_PATH, 'Search', '/?s=', '0 0 512 512') +
    icon_link('ic-heart', HEART_PATH, 'Favorites', '/collection/', '0 0 512 512'),
    style={"display": ["flex"], "columnGap": ["6px"], "alignItems": ["center"]}, name='Header Icons')

# ---------- Apply header edits ----------
hdr = open('reference/tp-header.html', encoding='utf-8').read()

# a. menu items swap (between outer ul open and the sliding-panel block)
pat = re.compile(r'(<ul class="gs_menu_a2940 gsbp-d1da3f6">).*?(</ul>\n<!-- /wp:greenshift-blocks/element -->\n\n<!-- wp:greenshift-blocks/element \{"id":"gsbp-caf1403")', re.DOTALL)
new_hdr, n1 = pat.subn(lambda m: m.group(1) + menu_items.rstrip('\n') + m.group(2), hdr)

# b. Download button -> icons
pat2 = re.compile(r'<!-- wp:greenshift-blocks/element \{"id":"gsbp-ba133a1".*?<!-- /wp:greenshift-blocks/element -->', re.DOTALL)
new_hdr, n2 = pat2.subn(lambda m: icons.rstrip('\n'), new_hdr)

# c. topbar prepend
new_hdr = topbar + new_hdr

# e. agentic a11y: hamburger button label + expanded state, nav label, panel label
# hamburger block JSON: append aria attrs to its dynamicAttributes + HTML
new_hdr = new_hdr.replace(
    '"dynamicAttributes":[{"name":"data-panel-id","value":"#panel_gsbp-a2940"},',
    '"dynamicAttributes":[{"name":"aria-label","value":"Open menu"},{"name":"aria-expanded","value":"false"},{"name":"aria-controls","value":"panel_gsbp-a2940"},{"name":"data-panel-id","value":"#panel_gsbp-a2940"},')
new_hdr = new_hdr.replace(
    '<button class="gs_hamburger_cross gs-nav-trigger-panel gsbp-852957d" type="button" data-panel-id=',
    '<button class="gs_hamburger_cross gs-nav-trigger-panel gsbp-852957d" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="panel_gsbp-a2940" data-panel-id=')
# nav landmark label
new_hdr = new_hdr.replace(
    '{"id":"gsbp-856969a","controlId":"a2940","tag":"nav","type":"inner","localId":"gsbp-856969a","isVariation":"navigation"',
    '{"id":"gsbp-856969a","controlId":"a2940","tag":"nav","type":"inner","localId":"gsbp-856969a","dynamicAttributes":[{"name":"aria-label","value":"Main"}],"isVariation":"navigation"')
new_hdr = new_hdr.replace('<nav><!-- wp:greenshift-blocks/element {"id":"gsbp-852957d"',
                          '<nav aria-label="Main"><!-- wp:greenshift-blocks/element {"id":"gsbp-852957d"')
# sliding panel label
new_hdr = new_hdr.replace('"type":"inner","animation":{"duration":800,"easing":"ease","type":"clip-down","onclass_active":true},"className":"control-a2940"',
                          '"dynamicAttributes":[{"name":"aria-label","value":"Mobile menu"}],"type":"inner","animation":{"duration":800,"easing":"ease","type":"clip-down","onclass_active":true},"className":"control-a2940"')
new_hdr = new_hdr.replace('class="control-a2940 gsbp-caf1403 alignfull" id="panel_gsbp-a2940">',
                          'class="control-a2940 gsbp-caf1403 alignfull" id="panel_gsbp-a2940" aria-label="Mobile menu">')

# d. header wrapper: cream bg
old_open = '{"align":"full","style":{"spacing":{"margin":{"top":"0","bottom":"0"},"padding":{"top":"20px","bottom":"20px"}},"border":{"bottom":{"color":"#00000012","width":"1px"}}}'
new_open = '{"align":"full","style":{"color":{"background":"#fbf6ec"},"spacing":{"margin":{"top":"0","bottom":"0"},"padding":{"top":"20px","bottom":"20px"}},"border":{"bottom":{"color":"#7c8b5426","width":"1px"}}}'
n3 = new_hdr.count(old_open)
new_hdr = new_hdr.replace(old_open, new_open)
old_div = 'style="border-bottom-color:#00000012;border-bottom-width:1px;margin-top:0;margin-bottom:0;padding-top:20px;padding-bottom:20px"'
new_div = 'class="wp-block-group alignfull has-background" style="background-color:#fbf6ec;border-bottom-color:#7c8b5426;border-bottom-width:1px;margin-top:0;margin-bottom:0;padding-top:20px;padding-bottom:20px"'
new_hdr = new_hdr.replace('class="wp-block-group alignfull" ' + old_div, new_div)

open('output/header.html', 'w', encoding='utf-8').write(new_hdr)
print('header: menu swap', n1, '| download->icons', n2, '| wrapper restyle', n3)

# ---------- Footer ----------
VAR_MUTED = 'var(--gt-muted, #8c8172)'
def flink(seed, label, href):
    return block(seed, 'a', text=label, extra={"href": href}, html_attrs=f'href="{href}"',
                 style={"color": [VAR_MUTED], "fontSize": ["14px"], "textDecoration": ["none"],
                        "color_hover": ["var(--gt-purple, #7e5aa6)"], "transition": ["color 0.2s ease"]})

def fcolhead(seed, label):
    return block(seed, 'div', text=label,
                 style={"fontSize": ["12px"], "fontWeight": ["600"], "letterSpacing": ["1.4px"],
                        "textTransform": ["uppercase"], "color": ["var(--gt-ink, #33291f)"], "marginBottom": ["1rem"]})

logo_json = json.dumps({"id": sid('ftlogoi'), "tag": "img", "localId": sid('ftlogoi'),
    "src": f"{U}/brand-logo.png", "alt": "Marigold & Fern", "originalWidth": 348, "originalHeight": 200,
    "styleAttributes": {"width": ["150px"], "height": ["auto"], "marginBottom": ["1.2rem"]}, "CSSRender": True}).replace('--', D)
logo_img = (f'<!-- wp:greenshift-blocks/element {logo_json} -->\n'
            f'<img class="{sid("ftlogoi")}" src="{U}/brand-logo.png" alt="Marigold & Fern" width="348" height="200" loading="lazy"/>\n'
            f'<!-- /wp:greenshift-blocks/element -->\n')

brand_col = block('ftbrand', 'div', inner=logo_img +
    block('ftblurb', 'p', text="Modern apparel &amp; accessories for today's woman. Simple, cozy, beautifully put-together — in Ashford, Kent.",
          style={"color": [VAR_MUTED], "fontSize": ["14px"], "maxWidth": ["24rem"], "marginBottom": ["0px"]}),
    style={"display": ["flex"], "flexDirection": ["column"], "alignItems": ["flex-start"]}, name='Brand')

explore_col = block('ftexplore', 'div', inner=
    fcolhead('ftexh', 'Explore') +
    block('ftexlinks', 'nav', html_attrs='aria-label="Footer navigation"',
          extra={"dynamicAttributes": [{"name": "aria-label", "value": "Footer navigation"}]}, inner=
        flink('ftl1', 'Home', '/') + flink('ftl2', 'Collection', '/collection/') +
        flink('ftl3', 'About', '/about/') + flink('ftl4', 'Contact', '/contact/'),
        style={"display": ["flex"], "flexDirection": ["column"], "rowGap": ["0.6rem"]}),
    style={"display": ["flex"], "flexDirection": ["column"]}, name='Explore')

visit_col = block('ftvisit', 'div', inner=
    fcolhead('ftvih', 'Visit') +
    block('ftvlines', 'div', inner=
        block('ftv1', 'div', text='18 Mill Street', style={"color": [VAR_MUTED], "fontSize": ["14px"]}) +
        block('ftv2', 'div', text='Ashford, Kent TN23 1AA', style={"color": [VAR_MUTED], "fontSize": ["14px"]}) +
        flink('ftv3', '01233 555 0142', 'tel:+441233555042') +
        flink('ftv4', 'hello@example.com', 'mailto:hello@example.com'),
        style={"display": ["flex"], "flexDirection": ["column"], "rowGap": ["0.6rem"]}),
    style={"display": ["flex"], "flexDirection": ["column"]}, name='Visit')

foot_top = block('fttop', 'div', inner=
    block('ftgrid', 'div', inner=brand_col + explore_col + visit_col,
          gclass='gt-footer-grid', name='Footer Grid'),
    style={"display": ["flex"], "justifyContent": ["center"], "paddingTop": ["3.5rem"], "paddingBottom": ["3rem"],
           "paddingLeft": ["min(3vw, 20px)"], "paddingRight": ["min(3vw, 20px)"], "backgroundColor": ["var(--gt-cream, #fbf6ec)"],
           "borderTop": ["1px solid rgba(124,139,84,0.15)"], "marginBlockStart": ["0px"]},
    name='Footer Top', alignfull=True)

foot_bottom = block('ftbot', 'div', inner=
    block('ftbotrow', 'div', inner=
        block('ftcopy', 'div', text='© 2026 Marigold & Fern', style={"fontSize": ["13px"], "color": [VAR_MUTED]}) +
        block('ftmade', 'div', text='Made with care in Ashford', style={"fontSize": ["13px"], "color": [VAR_MUTED]}),
        style={"maxWidth": ["100%"], "width": ["1290px"], "display": ["flex"], "justifyContent": ["space-between"],
               "flexWrap": ["wrap"], "rowGap": ["0.5rem"], "columnGap": ["1rem"]}, name='Bottom Row'),
    style={"display": ["flex"], "justifyContent": ["center"], "paddingTop": ["1.4rem"], "paddingBottom": ["1.4rem"],
           "paddingLeft": ["min(3vw, 20px)"], "paddingRight": ["min(3vw, 20px)"], "backgroundColor": ["var(--gt-cream, #fbf6ec)"],
           "borderTop": ["1px solid rgba(124,139,84,0.15)"], "marginBlockStart": ["0px"]},
    name='Footer Bottom', alignfull=True)

aria_js = """<!-- wp:html -->
<script>
document.addEventListener('click', function(e){
  var t = e.target.closest('.gs-nav-trigger-panel');
  if(!t) return;
  setTimeout(function(){
    t.setAttribute('aria-expanded', String(t.classList.contains('triggeractive')));
    t.setAttribute('aria-label', t.classList.contains('triggeractive') ? 'Close menu' : 'Open menu');
  }, 50);
});
</script>
<!-- /wp:html -->
"""
footer = foot_top + foot_bottom + aria_js
open('output/footer.html', 'w', encoding='utf-8').write(footer)
print('footer blocks:', footer.count('wp:greenshift-blocks/element'))
