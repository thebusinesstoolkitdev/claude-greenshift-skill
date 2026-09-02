# -*- coding: utf-8 -*-
"""
Convert every raster source to WebP, then upload with alt text.

WebP is not optional in this pipeline. It is 25-35% smaller than JPEG and far
smaller than PNG at the same quality, and image weight is normally the largest
single component of a page. `wp_api.upload_media()` converts anything raster it
is handed, so a stray PNG cannot reach the library by accident; run this first so
the sizing and quality are deliberate rather than defaults.

Nothing is ever upscaled. A source smaller than its display size is re-encoded at
its own size, because stretching it adds bytes and removes detail.

    python scripts/prep_images.py build              # input/raw -> assets/, all WebP
    python scripts/prep_images.py build --max 1600   # cap the long edge
    python scripts/prep_images.py upload             # assets/ -> media library
    python scripts/prep_images.py audit              # non-WebP already in the library
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wp_api import WP, encode_webp  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, 'input', 'raw')
OUT = os.path.join(HERE, 'assets')
MAP = os.path.join(HERE, 'reference', 'media-map.json')

RASTER = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')
QUALITY = 82          # lossy target for photographs; encode_webp() falls back to
                      # lossless when that comes out smaller (logos, flat graphics)
DEFAULT_MAX = 1600    # long edge; 2x a 800px display slot


def build(max_edge=DEFAULT_MAX):
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    if not os.path.isdir(RAW):
        raise SystemExit(f'no source directory: {RAW}')

    converted, copied = 0, 0
    for name in sorted(os.listdir(RAW)):
        src = os.path.join(RAW, name)
        stem, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext == '.svg':                      # vector: nothing to convert
            io.open(os.path.join(OUT, name), 'wb').write(io.open(src, 'rb').read())
            copied += 1
            continue
        if ext not in RASTER and ext != '.webp':
            continue

        img = Image.open(src)
        img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')
        w, h = img.size
        if max(w, h) > max_edge:               # never upscale, only cap
            scale = max_edge / float(max(w, h))
            img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

        dest = os.path.join(OUT, stem + '.webp')
        data, how = encode_webp(img, QUALITY)
        io.open(dest, 'wb').write(data)
        before, after = os.path.getsize(src), len(data)
        converted += 1
        warn = '  <- LARGER than source, check this one' if after > before else ''
        print(f'  {name:40} {w}x{h} -> {img.size[0]}x{img.size[1]}  '
              f'{before // 1024}kB -> {after // 1024}kB  {how}{warn}')

    print(f'\n{converted} converted to WebP, {copied} SVG copied -> {OUT}')
    print('Add alt text for each in reference/media-map.json, then: prep_images.py upload')


def upload():
    """Upload assets/ and record ids + alt text. Alt text is required, not optional."""
    wp = WP()
    existing = json.load(io.open(MAP, encoding='utf-8')) if os.path.exists(MAP) else {}
    missing = []
    for name in sorted(os.listdir(OUT)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in ('.webp', '.svg'):
            continue
        entry = existing.get(stem) or {}
        if not entry.get('alt'):
            missing.append(stem)
            continue
        if entry.get('id'):
            continue
        att = wp.upload_media(os.path.join(OUT, name))
        wp.post(f"wp/v2/media/{att['id']}", {'alt_text': entry['alt']})
        entry.update({'id': att['id'], 'url': att['source_url'],
                      'width': att['media_details'].get('width'),
                      'height': att['media_details'].get('height')})
        existing[stem] = entry
        print(f"  {stem:44} -> {att['id']}")

    json.dump(existing, io.open(MAP, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    if missing:
        print(f'\n{len(missing)} image(s) skipped with no alt text in media-map.json:')
        for m in missing:
            print('  ' + m)
        return 1
    return 0


def audit():
    """Anything raster and non-WebP already in the library, with its page usage."""
    wp = WP()
    items = wp.get('wp/v2/media?per_page=100&media_type=image&context=edit')
    bad = [m for m in items
           if m.get('mime_type') in ('image/jpeg', 'image/png')]
    noalt = [m for m in items if not (m.get('alt_text') or '').strip()]
    for m in bad:
        kb = (m.get('media_details', {}).get('filesize') or 0) // 1024
        print(f"  {m['mime_type']:11} {kb:6}kB  {m['source_url']}")
    print(f'\n{len(bad)} non-WebP image(s), {len(noalt)} without alt text, '
          f'of {len(items)} total')
    return 1 if bad else 0


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'build'
    if cmd == 'build':
        m = int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else DEFAULT_MAX
        build(m)
    else:
        sys.exit({'upload': upload, 'audit': audit}[cmd]())
