# -*- coding: utf-8 -*-
"""
Launch stack: install plugins, build a branded contact form, wire notifications.

    python launch.py plugins                  # install + activate the wordpress.org set, check Gravity Forms
    python launch.py form "Acme Ltd"          # create a branded contact form -> prints the embed
    python launch.py emails 3 info@acme.com   # brand the confirmation + both emails on form 3
    python launch.py check                    # Gravity Forms REST self-test: create, read, update, delete a probe form
    python launch.py seo                      # stage meta descriptions from page content

Forms are Gravity Forms, driven over its REST API v2 (`gf/v2`). Gravity Forms is a
licensed plugin, not on wordpress.org, so it cannot be installed over REST: upload the
zip once per site (Plugins -> Add New -> Upload, or `wp plugin install gravityforms.zip
--activate`), enter the licence, and enable the API under Forms -> Settings -> REST API.
Everything after that is scripted. WordPress application passwords authenticate; the
user's Gravity Forms capabilities are honoured, so use an administrator.

The plugin set is deliberately small. Anything the host already provides (caching,
security, backups on managed WordPress) is not duplicated here, check the host panel
before adding a caching or security plugin.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wp_api import WP, WPError  # noqa: E402

# wordpress.org plugins, installable over REST
PLUGINS = [
    ('fluent-smtp', 'FluentSMTP, reliable delivery, free'),
    ('seo-by-rank-math', 'Rank Math, sitemap, schema, meta'),
]

GF_MANUAL = (
    'Gravity Forms is licensed and not on wordpress.org, so REST cannot install it.\n'
    '  1. Plugins -> Add New -> Upload Plugin -> gravityforms.zip (or: wp plugin install '
    'gravityforms.zip --activate)\n'
    '  2. Forms -> Settings -> enter the licence key\n'
    '  3. Forms -> Settings -> REST API -> Enable access to the API\n'
    'then re-run: python scripts/launch.py check')


def plugins():
    wp = WP()
    have = {p['plugin'].split('/')[0]: p['status'] for p in wp.get('wp/v2/plugins')}
    print('already installed:', ', '.join(sorted(have)) or '(none)')
    for slug, why in PLUGINS:
        if have.get(slug) == 'active':
            print(f'  = {slug} already active')
            continue
        # Big plugins frequently time out with a 500 while the files land fine.
        entry = wp.install_plugin(slug, activate=True)
        print(f'  + {slug} -> {entry["status"]}   ({why})')

    state = wp.gf_state()
    print('  gravityforms:', state)
    if state != 'ready':
        print(GF_MANUAL)

    print('\nManual steps that cannot be scripted:')
    print('  1. Rank Math setup wizard (wp-admin -> Rank Math), no meta is output until it runs')
    print('  2. Settings -> Permalinks -> Save, to flush rewrite rules for the sitemap')
    print('  3. FluentSMTP -> choose a sending provider and authenticate')
    if state != 'ready':
        print('  4. Gravity Forms: upload, licence, enable the REST API (above)')


# ---------------------------------------------------------------------------
# form
# ---------------------------------------------------------------------------

# (kind, machine name, label, placeholder, required). The machine name is stored as the
# field's adminLabel so emails() can find the field ids later without guessing.
DEFAULT_FIELDS = [
    ('text', 'name', 'Name', 'Your name', True),
    ('phone', 'phone', 'Phone', '(optional)', False),
    ('email', 'email', 'Email', 'you@email.com', True),
    ('textarea', 'message', 'Message', 'How can we help?', False),
]


def gf_field(field_id, kind, name, label, placeholder, required):
    """One Gravity Forms field object. Ids are integers, assigned in order."""
    field = {
        'id': field_id, 'type': kind, 'label': label, 'adminLabel': name,
        'isRequired': bool(required), 'placeholder': placeholder,
        'size': 'large', 'visibility': 'visible', 'cssClass': f'gt-field gt-field-{name}',
        'inputs': None,
    }
    if kind == 'phone':
        field['phoneFormat'] = 'international'
    if kind == 'email':
        field['emailConfirmEnabled'] = False
    if kind == 'textarea':
        field['useRichTextEditor'] = False
    return field


def stable_id(*parts):
    """A 13-character id in the shape Gravity Forms uses for notifications and
    confirmations (PHP uniqid), but deterministic, so re-running emails() updates
    the same objects instead of adding new ones."""
    return hashlib.md5('|'.join(parts).encode()).hexdigest()[:13]


def form(title='Contact form', fields=DEFAULT_FIELDS, submit_text='Send Message'):
    """
    Create a contact form: fields, a default on-page confirmation, and an admin
    notification to the site's admin email. `emails()` brands all three afterwards.
    Returns the form id.
    """
    wp = WP()
    state = wp.gf_state()
    if state != 'ready':
        raise SystemExit(f'Gravity Forms is {state}.\n{GF_MANUAL}')

    built = [gf_field(i + 1, *spec) for i, spec in enumerate(fields)]
    conf_id = stable_id(title, 'confirmation')
    note_id = stable_id(title, 'admin')
    payload = {
        'title': title,
        'description': '',
        'labelPlacement': 'top_label',
        'descriptionPlacement': 'below',
        'subLabelPlacement': 'below',
        'cssClass': 'gt-form',
        'button': {'type': 'text', 'text': submit_text},
        'fields': built,
        'is_active': True,
        'confirmations': {
            conf_id: {'id': conf_id, 'name': 'Default Confirmation', 'isDefault': True,
                      'type': 'message', 'message': 'Thank you, message received.',
                      'disableAutoformat': False},
        },
        'notifications': {
            note_id: {'id': note_id, 'name': 'Admin Notification', 'isActive': True,
                      'event': 'form_submission', 'toType': 'email', 'to': '{admin_email}',
                      'subject': f'New message from {{{"Name"}:{built[0]["id"]}}}',
                      'message': '{all_fields}', 'disableAutoformat': False},
        },
    }
    created = wp.gf_create_form(payload)
    form_id = int(created['id'])
    print(f'form {form_id} created: {title}')
    print(f'embed as a block:  blocks.gravity_form({form_id})')
    print(f'or the shortcode:  [gravityform id="{form_id}" title="false" description="false" ajax="true"]')
    print('wrap the embed in a container with the gt-form-card class to inherit brand styling')
    return form_id


# ---------------------------------------------------------------------------
# emails
# ---------------------------------------------------------------------------

def _email_shell(inner, preheader, logo_url, business, address, hours):
    """Table-based HTML that survives Gmail/Outlook/Apple Mail."""
    return f'''<div style="display:none;max-height:0;overflow:hidden">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f2e8d6;padding:24px 0">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#fbf6ec;border-radius:16px;overflow:hidden;border:1px solid rgba(51,41,31,0.1)">
<tr><td align="center" style="padding:32px 32px 8px"><img src="{logo_url}" alt="{business}" width="140" style="display:block;width:140px;height:auto"/></td></tr>
<tr><td style="padding:8px 40px 32px;font-family:Georgia,serif;color:#33291f">{inner}</td></tr>
<tr><td style="padding:20px 40px;border-top:1px solid rgba(90,102,60,0.2);font-family:Arial,sans-serif;font-size:12px;color:#6e6456;text-align:center">
{business} · {address}<br/>{hours}
</td></tr>
</table></td></tr></table>'''


def field_ids(form_obj):
    """{adminLabel or lowercase label: field id} for a form object."""
    out = {}
    for f in form_obj.get('fields') or []:
        key = (f.get('adminLabel') or f.get('label') or '').strip().lower()
        if key:
            out[key] = str(f['id'])
    return out


def tag(ids, name):
    """Merge tag for a field: {Label:id}. The label part is cosmetic; the id binds."""
    fid = ids.get(name)
    if fid is None:
        raise SystemExit(f'form has no field with adminLabel or label {name!r}; got {sorted(ids)}')
    return '{%s:%s}' % (name.capitalize(), fid)


def emails(form_id, to_address, business='Our Shop', logo_url='', address='', hours='',
           phone='', collection_url=''):
    """Brand the on-page confirmation, the admin notification, and the client auto-reply.

    Gravity Forms keeps notifications and confirmations on the form object, keyed by
    id, and `PUT /gf/v2/forms/{id}` replaces the whole form. So: read, edit the two
    dicts, write back. Ids are derived from the names, so a re-run updates in place.
    """
    wp = WP()
    form_obj = wp.gf_form(form_id)
    ids = field_ids(form_obj)
    name_t, email_t, message_t = tag(ids, 'name'), tag(ids, 'email'), tag(ids, 'message')
    phone_t = tag(ids, 'phone') if 'phone' in ids else ''

    # --- on-page confirmation -------------------------------------------------
    confirmations = dict(form_obj.get('confirmations') or {})
    default = next((c for c in confirmations.values() if c.get('isDefault')), None)
    if default is None:
        cid = stable_id(form_obj.get('title', ''), 'confirmation')
        default = confirmations[cid] = {'id': cid, 'name': 'Default Confirmation', 'isDefault': True}
    default.update({
        'type': 'message', 'disableAutoformat': True,
        'message': (
            '<div style="text-align:center;padding:0.5rem 0">'
            '<div style="font-size:26px;line-height:1.2;margin-bottom:8px;'
            'font-family:var(--gt-font-heading,Georgia,serif);color:var(--gt-text,#33291f);'
            'font-weight:600">Thank you, message received</div>'
            '<div style="color:var(--gt-text-muted,#6e6456);font-size:15px">We will get back to you '
            f'within a day or two.{f" Need us sooner? Call {phone}." if phone else ""}</div></div>'),
    })

    def row_html(label, value):
        return (f'<tr><td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:11px;'
                f'letter-spacing:1px;text-transform:uppercase;color:#7e5aa6;width:90px;'
                f'vertical-align:top">{label}</td>'
                f'<td style="padding:8px 12px;font-family:Arial,sans-serif;font-size:14px;'
                f'color:#33291f">{value}</td></tr>')

    admin_inner = (
        '<h2 style="font-family:Georgia,serif;font-weight:600;font-size:24px;margin:0 0 6px;'
        'color:#33291f">New message from the website</h2>'
        '<p style="font-family:Arial,sans-serif;font-size:14px;color:#6e6456;margin:0 0 20px">'
        'Someone reached out through the contact form.</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f2e8d6;border-radius:12px;padding:8px">'
        + row_html('Name', name_t)
        + (row_html('Phone', phone_t) if phone_t else '')
        + row_html('Email', f'<a href="mailto:{email_t}" style="color:#7e5aa6">{email_t}</a>')
        + row_html('Message', message_t)
        + '</table>'
        '<p style="font-family:Arial,sans-serif;font-size:13px;color:#6e6456;margin:20px 0 0">'
        f'Reply directly to this email to answer {name_t}.</p>')

    cta = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto">'
           f'<tr><td style="border-radius:12px;background-color:#7e5aa6" align="center">'
           f'<a href="{collection_url}" style="display:inline-block;padding:13px 28px;'
           f'font-family:Arial,sans-serif;font-size:14px;color:#fbf6ec;text-decoration:none">'
           f'Browse the Collection</a></td></tr></table>') if collection_url else ''

    client_inner = (
        '<h2 style="font-family:Georgia,serif;font-weight:600;font-size:24px;margin:0 0 6px;'
        'color:#33291f">We got your message</h2>'
        '<p style="font-family:Arial,sans-serif;font-size:14px;color:#33291f;line-height:1.6;'
        f'margin:0 0 16px">Hi {name_t},</p>'
        '<p style="font-family:Arial,sans-serif;font-size:14px;color:#33291f;line-height:1.6;'
        f'margin:0 0 16px">Thanks for reaching out to {business}, your note landed safely and '
        'we will get back to you within a day or two.</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f2e8d6;border-radius:12px;padding:8px;margin:0 0 20px">'
        + row_html('You wrote', message_t) + '</table>' + cta)

    notifications = dict(form_obj.get('notifications') or {})
    # retire the stock admin notification created with the form, ours replaces it
    admin_id = stable_id(form_obj.get('title', ''), 'admin')
    client_id = stable_id(form_obj.get('title', ''), 'client')
    notifications[admin_id] = {
        'id': admin_id, 'name': 'Admin Notification', 'isActive': True, 'event': 'form_submission',
        'toType': 'email', 'to': to_address,
        'fromName': f'{business} Website', 'from': to_address, 'replyTo': email_t, 'bcc': '',
        'subject': f'New message from {name_t}',
        'message': _email_shell(admin_inner, f'New contact form message from {name_t}',
                                logo_url, business, address, hours),
        'disableAutoformat': True,
    }
    notifications[client_id] = {
        'id': client_id, 'name': 'Client Confirmation', 'isActive': True, 'event': 'form_submission',
        'toType': 'field', 'to': ids['email'],
        'fromName': business, 'from': to_address, 'replyTo': to_address, 'bcc': '',
        'subject': f'We got your message, {business}',
        'message': _email_shell(client_inner, f'Thanks {name_t}. We will be in touch',
                                logo_url, business, address, hours),
        'disableAutoformat': True,
    }

    form_obj['confirmations'] = confirmations
    form_obj['notifications'] = notifications
    wp.gf_update_form(form_id, form_obj)

    back = wp.gf_form(form_id)
    print('confirmation message updated')
    print('admin notification ->', to_address)
    print('client confirmation -> submitter')
    print('notifications now:', [(k[:6], v.get('name'), v.get('to')) for k, v in (back.get('notifications') or {}).items()])


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def check():
    """Prove the Gravity Forms REST path end to end without sending a single email:
    create a probe form, read it back, update it, delete it permanently."""
    wp = WP()
    state = wp.gf_state()
    print('gravityforms:', state)
    if state != 'ready':
        print(GF_MANUAL)
        return 1
    probe = wp.gf_create_form({
        'title': 'greenlight probe (safe to delete)', 'labelPlacement': 'top_label',
        'button': {'type': 'text', 'text': 'Send'},
        'fields': [gf_field(1, 'text', 'name', 'Name', '', True),
                   gf_field(2, 'email', 'email', 'Email', '', True)],
        'confirmations': {'p' * 13: {'id': 'p' * 13, 'name': 'Default Confirmation',
                                     'isDefault': True, 'type': 'message', 'message': 'ok'}},
        'notifications': {},
    })
    fid = int(probe['id'])
    ok = True
    try:
        back = wp.gf_form(fid)
        fields = {str(f['id']): f['type'] for f in back.get('fields') or []}
        print('  created form %d, fields back: %s' % (fid, fields))
        ok &= fields == {'1': 'text', '2': 'email'}
        back['title'] = 'greenlight probe (updated)'
        back['notifications'] = {'n' * 13: {'id': 'n' * 13, 'name': 'Probe', 'isActive': False,
                                            'event': 'form_submission', 'toType': 'email',
                                            'to': '{admin_email}', 'subject': 'x', 'message': '{all_fields}'}}
        wp.gf_update_form(fid, back)
        again = wp.gf_form(fid)
        print('  updated title: %r, notifications: %s' % (again.get('title'), list((again.get('notifications') or {}).keys())))
        ok &= again.get('title') == 'greenlight probe (updated)' and 'n' * 13 in (again.get('notifications') or {})
    finally:
        wp.gf_delete_form(fid, force=True)
        gone = str(fid) not in {str(f.get('id')) for f in wp.gf_forms()}
        print('  probe deleted:', gone)
        ok &= gone
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# seo
# ---------------------------------------------------------------------------

def seo(descriptions=None):
    """
    Stage meta descriptions. Rank Math does not expose rank_math_* meta over REST until
    its wizard has run, but its default template falls back to the excerpt, which is a
    first-class REST field, so writing excerpts works before or after the wizard.
    """
    wp = WP()
    pages = wp.get('wp/v2/pages?per_page=100&status=publish,draft')
    for page in pages:
        text = (descriptions or {}).get(page['slug'])
        if not text:
            print(f'  skip {page["slug"]} (no description supplied)')
            continue
        wp.post(f'wp/v2/pages/{page["id"]}', {'excerpt': text})
        print(f'  set {page["slug"]}: {text[:60]}…')


if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) > 1 else 'plugins'
    if command == 'plugins':
        plugins()
    elif command == 'form':
        form(sys.argv[2] if len(sys.argv) > 2 else 'Contact form')
    elif command == 'emails':
        emails(int(sys.argv[2]), sys.argv[3])
    elif command == 'check':
        sys.exit(check())
    elif command == 'seo':
        seo()
    else:
        print(__doc__)
