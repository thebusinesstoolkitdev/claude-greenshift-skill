# -*- coding: utf-8 -*-
# EXAMPLE — a real four-page build, with the client details swapped out.
# Copy into your project and adapt. The reusable primitives live in
# scripts/blocks.py; this file shows how a whole page is assembled.
"""Generate Greenshift block markup for About / Collection / Contact pages."""
import json, hashlib, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

U = "https://example.com/wp-content/uploads/2025/01"
D = "\\u002d\\u002d"  # escaped -- for block comment JSON

_used = set()
def gid(seed):
    h = hashlib.md5(seed.encode()).hexdigest()
    for i in range(0, 25):
        c = 'gsbp-' + h[i:i+7]
        if c not in _used:
            _used.add(c)
            return c
    raise Exception('id collision: ' + seed)

_ids = {}
def sid(seed):
    if seed not in _ids:
        _ids[seed] = gid(seed)
    return _ids[seed]

def block(seed, tag, inner=None, text=None, style=None, extra=None, html_attrs='', gclass='', name=None, alignfull=False):
    i = sid(seed)
    j = {"id": i}
    if text is not None:
        j["textContent"] = text
    if tag != 'div':
        j["tag"] = tag
    if inner is not None:
        j["type"] = "inner"
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
    cls = i + (' ' + gclass if gclass else '') + (' alignfull' if alignfull else '')
    attrs = (' ' + html_attrs) if html_attrs else ''
    if text is not None:
        h = f'<{tag} class="{cls}"{attrs}>{text}</{tag}>'
    else:
        h = f'<{tag} class="{cls}"{attrs}>\n{inner or ""}\n</{tag}>'
    return f'<!-- wp:greenshift-blocks/element {js} -->\n{h}\n<!-- /wp:greenshift-blocks/element -->\n'

def img(seed, src, alt, w, h, style):
    i = sid(seed)
    j = {"id": i, "tag": "img", "localId": i, "src": src, "alt": alt,
         "originalWidth": w, "originalHeight": h, "styleAttributes": style, "CSSRender": "1"}
    js = json.dumps(j, ensure_ascii=False).replace('--', D)
    return (f'<!-- wp:greenshift-blocks/element {js} -->\n'
            f'<img class="{i}" src="{src}" alt="{alt}" width="{w}" height="{h}" loading="lazy"/>\n'
            f'<!-- /wp:greenshift-blocks/element -->\n')

# Scripts, JSON-LD and shortcodes only. Page content goes in element blocks:
# core/html is uneditable in the block editor, ignores the stylebook, and is
# skipped by every check. scripts/blocks.py raw_html() enforces this.
def rawhtml(content):
    return f'<!-- wp:html -->\n{content}\n<!-- /wp:html -->\n'

VAR_CREAM = 'var(--gt-cream, #fbf6ec)'
VAR_SAND = 'var(--gt-sand, #f2e8d6)'
VAR_MUTED = 'var(--gt-muted, #8c8172)'

def section(seed, inner, bg=None, bgimg=None, pad='clamp(3.5rem, 7vw, 5rem)', name=None):
    style = {"display": ["flex"], "justifyContent": ["center"], "flexDirection": ["column"],
             "alignItems": ["center"], "paddingLeft": ["min(3vw, 20px)"], "paddingRight": ["min(3vw, 20px)"],
             "paddingTop": [pad], "paddingBottom": [pad], "marginBlockStart": ["0px"]}
    if bg:
        style["backgroundColor"] = [bg]
    if bgimg:
        style["backgroundImage"] = [f"url({bgimg})"]
        style["backgroundSize"] = ["cover"]
        style["backgroundPosition"] = ["center center"]
    return block(seed, 'section', inner=inner, style=style,
                 extra={"isVariation": "contentwrapper"}, name=name, alignfull=True)

def content(seed, inner, extra_style=None, name=None):
    style = {"maxWidth": ["100%"], "width": ["1290px"], "display": ["flex"],
             "flexDirection": ["column"], "alignItems": ["center"]}
    if extra_style:
        style.update(extra_style)
    return block(seed, 'div', inner=inner, style=style, name=name)

def hero_card(seed, eyebrow_cls, eyebrow, h1txt, lead, maxw='640px', align='center'):
    inner = block(seed + 'eb', 'div', text=eyebrow, gclass=eyebrow_cls, name='Eyebrow')
    inner += block(seed + 'h1', 'h1', text=h1txt, style={"marginTop": ["0px"], "marginBottom": ["1rem"], "textAlign": [align]})
    inner += block(seed + 'ld', 'p', text=lead, gclass='gt-lead', style={"textAlign": [align], "marginBottom": ["0px"]})
    st = {"maxWidth": [maxw], "width": ["100%"]}
    if align == 'left':
        st["alignItems"] = ["flex-start"]
    return block(seed + 'card', 'div', inner=inner, style=st, gclass='gt-card-overlay', name='Hero Card')

def btn(seed, text, href, primary=True, attrs=''):
    extra = {"href": href}
    if 'target="_blank"' in attrs:
        extra["linkNewWindow"] = True
    return block(seed, 'a', text=text, gclass='gt-btn-primary' if primary else 'gt-btn-outline',
                 extra=extra, html_attrs=(f'href="{href}" ' + attrs).strip())

def btnrow(seed, buttons):
    return block(seed, 'div', inner=''.join(buttons),
                 style={"display": ["flex"], "columnGap": ["1rem"], "rowGap": ["1rem"],
                        "flexWrap": ["wrap"], "justifyContent": ["center"]}, name='Buttons')

def cta_purple(seed, h2txt, para, buttons):
    inner = block(seed + 'h2', 'h2', text=h2txt, style={"marginTop": ["0px"], "marginBottom": ["1rem"], "textAlign": ["center"]})
    inner += block(seed + 'p', 'p', text=para, style={"color": [VAR_MUTED], "textAlign": ["center"], "marginBottom": ["1.8rem"]})
    inner += btnrow(seed + 'btns', buttons)
    card = block(seed + 'card', 'div', inner=inner, style={"maxWidth": ["640px"], "width": ["100%"]},
                 gclass='gt-card-overlay', name='CTA Card')
    return section(seed + 'sec', card, bgimg=f"{U}/gt-cta-purple-bg.jpg", pad='clamp(3.75rem, 7vw, 5.5rem)', name='CTA Section')

pages = {}

# ============ ABOUT ============
s = 'ab1'
hero = section(s + 'hero',
    block(s + 'wrap', 'div',
          inner=hero_card(s, 'gt-eyebrow', 'Our Story', 'A little shop with a big welcome',
                          'A cozy, casual spot for modern apparel and accessories — curated with care, in the heart of Ashford.',
                          maxw='560px', align='left'),
          style={"maxWidth": ["100%"], "width": ["1290px"], "display": ["flex"], "justifyContent": ["flex-start"]},
          name='Hero Row'),
    bgimg=f"{U}/gt-mural-bg.jpg", pad='clamp(4rem, 8vw, 6rem)', name='About Hero')

who_text = block(s + 'wt', 'div', inner=
    block(s + 'web', 'div', text='Who We Are', gclass='gt-eyebrow', name='Eyebrow') +
    block(s + 'wh2', 'h2', text='Effortless style, minus the fuss', style={"marginTop": ["0px"], "marginBottom": ["1.2rem"]}) +
    block(s + 'wp1', 'p', text='At Marigold & Fern, we believe getting dressed should feel easy and fun. We curate high-quality, versatile pieces that move with the rhythm of your life — so you always feel polished, comfy and put-together.', style={"color": [VAR_MUTED], "marginBottom": ["1rem"]}) +
    block(s + 'wp2', 'p', text="More than a shop, it's a friendly little spot to browse, get a second opinion, and leave with something you love.", style={"color": [VAR_MUTED], "marginBottom": ["2rem"]}) +
    btn(s + 'wbtn', 'Browse the Collection', '/collection'),
    style={"display": ["flex"], "flexDirection": ["column"], "alignItems": ["flex-start"]}, name='Who Text')

who = section(s + 'who',
    block(s + 'wgrid', 'div', inner=
        img(s + 'wimg', f"{U}/gt-store-interior.jpg", 'Inside the Marigold & Fern shop', 1200, 1487,
            {"width": ["100%"], "height": ["auto"], "objectFit": ["cover"], "borderRadius": ["16px"]}) + who_text,
        style={"maxWidth": ["1290px"]}, gclass='gt-grid-even', name='Who Grid'),
    bg=VAR_CREAM, name='Who We Are')

def mv_card(seed, icon, label, labelcolor, h3txt, para):
    return block(seed, 'div', inner=
        img(seed + 'i', f"{U}/{icon}", '', 108, 108, {"width": ["44px"], "height": ["44px"], "marginBottom": ["1rem"]}) +
        block(seed + 'l', 'div', text=label, style={"fontSize": ["12px"], "fontWeight": ["600"], "letterSpacing": ["1.9px"], "textTransform": ["uppercase"], "color": [labelcolor], "marginBottom": ["0.6rem"]}) +
        block(seed + 'h', 'h3', text=h3txt, style={"marginTop": ["0px"], "marginBottom": ["0.7rem"]}) +
        block(seed + 'p', 'p', text=para, style={"color": [VAR_MUTED], "fontSize": ["15px"], "marginBottom": ["0px"]}),
        gclass='gt-card-soft', style={"textAlign": ["left"]}, name=label)

mission = section(s + 'mv',
    content(s + 'mvc',
        block(s + 'mveb', 'div', text="What we're about", gclass='gt-eyebrow-accent', name='Eyebrow') +
        block(s + 'mvh2', 'h2', text='Our mission & vision', style={"marginTop": ["0px"], "marginBottom": ["2.4rem"], "textAlign": ["center"]}) +
        block(s + 'mvgrid', 'div', inner=
            mv_card(s + 'mc1', 'gt-icon-pansy-purple.png', 'Our Mission', 'var(--gt-purple, #7e5aa6)', 'Make dressing well easy', 'To take the guesswork out of getting dressed — with versatile, quality pieces that help every woman feel confident, comfy and put-together.') +
            mv_card(s + 'mc2', 'gt-icon-pansy-orange.png', 'Our Vision', 'var(--gt-accent, #e27b4b)', 'A welcoming style home', 'To be the friendly neighborhood spot where great style, good brands and a warm hello all come together.'),
            gclass='gt-grid-2', name='MV Grid')),
    bg=VAR_SAND, name='Mission Vision')

def love_card(seed, icon, h3txt, para):
    return block(seed, 'div', inner=
        img(seed + 'i', f"{U}/{icon}", '', 108, 108, {"width": ["54px"], "height": ["54px"], "marginBottom": ["1rem"], "marginLeft": ["auto"], "marginRight": ["auto"]}) +
        block(seed + 'h', 'h3', text=h3txt, style={"marginTop": ["0px"], "marginBottom": ["0.6rem"], "textAlign": ["center"]}) +
        block(seed + 'p', 'p', text=para, style={"color": [VAR_MUTED], "fontSize": ["14px"], "textAlign": ["center"], "marginBottom": ["0px"]}),
        gclass='gt-card-sand', name=h3txt)

love = section(s + 'love',
    content(s + 'lovec',
        block(s + 'lvh2', 'h2', text="What you'll love about us", style={"marginTop": ["0px"], "marginBottom": ["2.4rem"], "textAlign": ["center"]}) +
        block(s + 'lvgrid', 'div', inner=
            love_card(s + 'lc1', 'gt-icon-pansy-purple.png', 'Curated', 'Hand-picked pieces from brands we genuinely love.') +
            love_card(s + 'lc2', 'gt-icon-pansy-orange.png', 'Versatile', 'Easy staples that mix, match and go anywhere.') +
            love_card(s + 'lc3', 'gt-icon-pansy-yellow.png', 'Comfy', "Feel-good fits you'll actually want to wear.") +
            love_card(s + 'lc4', 'gt-icon-garland.png', 'Welcoming', 'A relaxed, friendly place to shop and hang out.'),
            gclass='gt-grid-4', name='Love Grid')),
    bg=VAR_CREAM, name='What Youll Love')

cta_a = cta_purple(s + 'cta', 'Come say hello', '18 Mill Street, Ashford, Kent TN23 1AA',
    [btn(s + 'cb1', 'Get Directions', 'https://maps.google.com/?q=18+Mill+Street,+Ashford,+Kent+TN23+1AA', True, 'target="_blank" rel="noopener"'),
     btn(s + 'cb2', 'Contact Us', '/contact', False)])

pages['about'] = block(s + 'page', 'div', inner=hero + who + mission + love + cta_a,
                       style={"marginBlockStart": ["0px"], "backgroundColor": [VAR_CREAM]}, name='Page Wrapper', alignfull=True)

# ============ COLLECTION ============
s = 'cl1'
hero_c = section(s + 'hero', hero_card(s, 'gt-eyebrow', 'The Collection', 'Shop the collection',
    'A curated edit of modern apparel and accessories — versatile pieces made to be worn again and again. Browse online, shop in-store.'),
    bgimg=f"{U}/gt-mural-bg.jpg", pad='clamp(3.75rem, 7vw, 5.5rem)', name='Collection Hero')

chips = [('All','all'),('Dresses','dresses'),('Tops','tops'),('Knitwear','knitwear'),('Outerwear','outerwear'),('Accessories','accessories'),('New Arrivals','new-arrivals')]
chiprow = block(s + 'chips', 'div', inner=''.join(
    block(s + 'ch' + c, 'button', text=c, gclass='gt-chip',
          extra={"formAttributes": {"type": "button"},
                 "dynamicAttributes": [{"name": "data-filter", "value": slug},
                                        {"name": "aria-pressed", "value": str(slug == "all").lower()}]},
          html_attrs=f'type="button" data-filter="{slug}" aria-pressed="{str(slug=="all").lower()}"') for c, slug in chips),
    style={"display": ["flex"], "columnGap": ["0.7rem"], "rowGap": ["0.7rem"], "flexWrap": ["wrap"],
           "justifyContent": ["center"], "marginBottom": ["2.6rem"]},
    extra={"dynamicAttributes": [{"name": "role", "value": "group"},
                                  {"name": "aria-label", "value": "Filter pieces by category"}]},
    html_attrs='role="group" aria-label="Filter pieces by category"', name='Filter Chips')

prods = [("gt-prod-ivory-knit.jpg", "Ivory Knit", "Knitwear", 584, 752),
         ("gt-prod-silk-blouse.jpg", "Silk Tie Blouse", "Tops", 584, 752),
         ("gt-prod-emerald-dress.jpg", "Emerald Wrap Dress", "Dresses", 584, 752),
         ("gt-prod-tailored-blazer.jpg", "Tailored Blazer", "New In", 584, 752),
         ("gt-prod-rust-midi.jpg", "Rust Midi Dress", "Dresses", 624, 804),
         ("gt-prod-camel-trench.jpg", "Camel Trench", "Outerwear", 624, 804),
         ("gt-prod-mustard-cardigan.jpg", "Mustard Cardigan", "Knitwear", 624, 804),
         ("gt-prod-olive-blazer.jpg", "Olive Blazer", "Outerwear", 624, 804)]
cards = ''
catmap = {'Knitwear':'knitwear','Tops':'tops','Dresses':'dresses','New In':'new-arrivals','Outerwear':'outerwear','Accessories':'accessories'}
for fn, nm, cat, w, h in prods:
    seed = s + 'pc' + nm
    cards += block(seed, 'article', html_attrs=f'data-cat="{catmap[cat]}"',
        extra={"dynamicAttributes": [{"name": "data-cat", "value": catmap[cat]}]}, inner=
        img(seed + 'i', f"{U}/{fn}", nm, w, h, {"width": ["100%"], "height": ["auto"], "objectFit": ["cover"], "borderRadius": ["10px"], "marginBottom": ["1rem"]}) +
        block(seed + 't', 'h3', text=nm, style={"marginTop": ["0px"], "marginBottom": ["0.3rem"], "textAlign": ["center"]}) +
        block(seed + 'c', 'div', text=cat, style={"fontSize": ["12px"], "letterSpacing": ["0.7px"], "textTransform": ["uppercase"], "color": [VAR_MUTED], "textAlign": ["center"]}),
        style={"display": ["flex"], "flexDirection": ["column"], "alignItems": ["center"]}, name=nm)

empty_state = rawhtml('<p id="gt-filter-empty" hidden style="text-align:center;color:var(--gt-muted,#6e6456);padding:2rem 0">Nothing in this category yet — check back soon.</p>')
live_region = rawhtml('<div id="gt-filter-status" aria-live="polite" class="screen-reader-text" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)"></div>')
filter_js = rawhtml('''<script>
document.addEventListener('click', function(e){
  var chip = e.target.closest('[data-filter]');
  if(!chip) return;
  var f = chip.getAttribute('data-filter');
  var chips = document.querySelectorAll('[data-filter]');
  var cards = document.querySelectorAll('[data-cat]');
  var shown = 0;
  chips.forEach(function(c){ c.setAttribute('aria-pressed', String(c === chip)); });
  cards.forEach(function(card){
    var show = (f === 'all') || card.getAttribute('data-cat') === f;
    card.style.display = show ? '' : 'none';
    if(show) shown++;
  });
  var empty = document.getElementById('gt-filter-empty');
  if(empty) empty.hidden = shown > 0;
  var status = document.getElementById('gt-filter-status');
  if(status) status.textContent = shown + ' piece' + (shown === 1 ? '' : 's') + ' shown';
});
</script>''')
sr_h2 = block(s + 'srh2', 'h2', text='All pieces', gclass='gt-sr-only')
grid_c = section(s + 'grid', content(s + 'gc', sr_h2 + chiprow +
    block(s + 'pgrid', 'div', inner=cards, gclass='gt-grid-4', name='Product Grid') + empty_state + live_region + filter_js),
    bg=VAR_CREAM, name='Products')

cta_c = cta_purple(s + 'cta', 'Want a hand styling it?', "Pop in and we'll help you put together looks you'll love.",
    [btn(s + 'cb1', 'Visit the Store', 'https://maps.google.com/?q=18+Mill+Street,+Ashford,+Kent+TN23+1AA', True, 'target="_blank" rel="noopener"'),
     btn(s + 'cb2', 'Contact Us', '/contact', False)])

pages['collection'] = block(s + 'page', 'div', inner=hero_c + grid_c + cta_c,
                            style={"marginBlockStart": ["0px"], "backgroundColor": [VAR_CREAM]}, name='Page Wrapper', alignfull=True)

# ============ CONTACT ============
s = 'ct1'
hero_t = section(s + 'hero', hero_card(s, 'gt-eyebrow', 'Say Hello', "Let's talk",
    "Questions about a piece, your size, or store hours? Drop us a line or come on in — we'd love to help."),
    bgimg=f"{U}/gt-mural-bg.jpg", pad='clamp(3.75rem, 7vw, 5.5rem)', name='Contact Hero')

def info_row(seed, icon, label, lines):
    txt = ''.join(block(seed + 't' + str(i), 'div', text=l, style={"fontSize": ["15px"], "color": ["var(--gt-ink, #33291f)"]}) for i, l in enumerate(lines))
    return block(seed, 'div', inner=
        img(seed + 'i', f"{U}/{icon}", '', 108, 108, {"width": ["32px"], "height": ["32px"], "flexShrink": ["0"]}) +
        block(seed + 'col', 'div', inner=
            block(seed + 'l', 'div', text=label, style={"fontSize": ["12px"], "fontWeight": ["600"], "letterSpacing": ["1.2px"], "textTransform": ["uppercase"], "color": ["var(--gt-purple, #7e5aa6)"], "marginBottom": ["0.2rem"]}) + txt,
            style={"display": ["flex"], "flexDirection": ["column"]}),
        style={"display": ["flex"], "columnGap": ["1rem"], "alignItems": ["flex-start"], "marginBottom": ["1.4rem"]}, name=label)

left = block(s + 'left', 'div', inner=
    block(s + 'leb', 'div', text='Visit & Reach Us', gclass='gt-eyebrow', name='Eyebrow') +
    block(s + 'lh2', 'h2', text="We're a friendly little shop", style={"marginTop": ["0px"], "marginBottom": ["1rem"]}) +
    block(s + 'lp', 'p', text="Prefer in person? Come browse and say hi. We're always happy to help you find something you love.", style={"color": [VAR_MUTED], "marginBottom": ["1.8rem"]}) +
    info_row(s + 'ir1', 'gt-icon-pansy-purple.png', 'Visit', ['18 Mill Street', 'Ashford, Kent 72335']) +
    info_row(s + 'ir2', 'gt-icon-pansy-orange.png', 'Call', ['01233 555 0142']) +
    info_row(s + 'ir3', 'gt-icon-pansy-yellow.png', 'Email', ['hello@example.com']) +
    info_row(s + 'ir4', 'gt-icon-garland.png', 'Hours', ['Mon – Sat · 10am – 6pm', 'Sunday · Closed']),
    style={"display": ["flex"], "flexDirection": ["column"], "alignItems": ["flex-start"]}, name='Contact Info')

form_html = rawhtml('[fluentform id="3"]')

right = block(s + 'right', 'div', inner=
    block(s + 'rh2', 'h2', text='Send us a message', style={"marginTop": ["0px"], "marginBottom": ["0.4rem"]}) +
    block(s + 'rp', 'p', text="We'll get back to you within a day or two.", style={"color": [VAR_MUTED], "fontSize": ["14px"], "marginBottom": ["1.6rem"]}) + form_html,
    gclass='gt-form-card', style={"backgroundColor": [VAR_SAND], "borderRadius": ["16px"], "paddingTop": ["2.4rem"], "paddingBottom": ["2.4rem"], "paddingLeft": ["clamp(1.2rem, 3vw, 2.2rem)"], "paddingRight": ["clamp(1.2rem, 3vw, 2.2rem)"], "boxSizing": ["border-box"]}, name='Form Card')

main_ct = section(s + 'main',
    block(s + 'mgrid', 'div', inner=left + right,
          style={"maxWidth": ["1290px"]}, gclass='gt-grid-split', name='Contact Grid'),
    bg=VAR_CREAM, name='Contact Main')

cta_t = cta_purple(s + 'cta', 'Find us on Mill Street', '18 Mill Street, Ashford, Kent TN23 1AA',
    [btn(s + 'cb1', 'Get Directions', 'https://maps.google.com/?q=18+Mill+Street,+Ashford,+Kent+TN23+1AA', True, 'target="_blank" rel="noopener"'),
     btn(s + 'cb2', 'Call the Shop', 'tel:+441233555042', False)])

pages['contact'] = block(s + 'page', 'div', inner=hero_t + main_ct + cta_t,
                         style={"marginBlockStart": ["0px"], "backgroundColor": [VAR_CREAM]}, name='Page Wrapper', alignfull=True)

os.makedirs('output', exist_ok=True)
for name, html in pages.items():
    open(f'output/{name}.html', 'w', encoding='utf-8').write(html)
    print(name, len(html) // 1024, 'KB, blocks:', html.count('wp:greenshift-blocks/element'))
