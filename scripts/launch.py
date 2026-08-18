# -*- coding: utf-8 -*-
"""
Launch stack: install plugins, build a branded contact form, wire notifications.

    python launch.py plugins                  # install + activate the standard set
    python launch.py form "Acme Ltd"          # create a branded contact form -> prints shortcode
    python launch.py emails 3 info@acme.com   # brand the confirmation + both emails
    python launch.py seo                      # stage meta descriptions from page content

The plugin set is deliberately small. Anything the host already provides (caching,
security, backups on managed WordPress) is not duplicated here — check the host panel
before adding a caching or security plugin.
"""
import json
import sys

sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from wp_api import WP, WPError  # noqa: E402

PLUGINS = [
    ('fluentform', 'Fluent Forms — contact forms'),
    ('fluent-smtp', 'FluentSMTP — reliable delivery, free'),
    ('seo-by-rank-math', 'Rank Math — sitemap, schema, meta'),
]


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
    print('\nManual steps that cannot be scripted:')
    print('  1. Rank Math setup wizard (wp-admin -> Rank Math) — nothing is output until it runs')
    print('  2. Settings -> Permalinks -> Save, to flush rewrite rules for the sitemap')
    print('  3. FluentSMTP -> choose a sending provider and authenticate')


FIELD_TEMPLATES = {
    'text': lambda name, label, placeholder, required: {
        'element': 'input_text',
        'attributes': {'type': 'text', 'name': name, 'value': '', 'id': '', 'class': '',
                       'placeholder': placeholder},
        'settings': {'container_class': '', 'label': label, 'label_placement': '',
                     'help_message': '', 'admin_field_label': label,
                     'validation_rules': {'required': {'value': required,
                                                       'message': 'This field is required'}},
                     'conditional_logics': []},
        'editor_options': {'title': label, 'icon_class': 'ff-edit-text', 'template': 'inputText'},
    },
    'email': lambda name, label, placeholder, required: {
        'element': 'input_email',
        'attributes': {'type': 'email', 'name': name, 'value': '', 'id': '', 'class': '',
                       'placeholder': placeholder},
        'settings': {'container_class': '', 'label': label, 'label_placement': '',
                     'help_message': '', 'admin_field_label': label,
                     'validation_rules': {
                         'required': {'value': required, 'message': 'This field is required'},
                         'email': {'value': True, 'message': 'This field must contain a valid email'}},
                     'conditional_logics': []},
        'editor_options': {'title': label, 'icon_class': 'ff-edit-email', 'template': 'inputText'},
    },
    'textarea': lambda name, label, placeholder, required: {
        'element': 'textarea',
        'attributes': {'name': name, 'value': '', 'id': '', 'class': '',
                       'placeholder': placeholder, 'rows': 5, 'cols': 2},
        'settings': {'container_class': '', 'label': label, 'label_placement': '',
                     'help_message': '', 'admin_field_label': label,
                     'validation_rules': {'required': {'value': required,
                                                       'message': 'This field is required'}},
                     'conditional_logics': []},
        'editor_options': {'title': label, 'icon_class': 'ff-edit-textarea',
                           'template': 'inputTextarea'},
    },
}

DEFAULT_FIELDS = [
    ('text', 'name', 'Name', 'Your name', True),
    ('text', 'phone', 'Phone', '(optional)', False),
    ('email', 'email', 'Email', 'you@email.com', True),
    ('textarea', 'message', 'Message', 'How can we help?', False),
]


def form(title='Contact form', fields=DEFAULT_FIELDS, submit_text='Send Message'):
    """
    Create a contact form.

    Fluent Forms rejects `POST /forms` without one of its own template keys, so the
    reliable path is: duplicate the bundled demo form, then overwrite its fields.
    """
    wp = WP()
    existing = wp.ff_forms()
    demo = next((f for f in existing if f['title'] == 'Contact Form Demo'), None)
    if demo is None:
        raise SystemExit('No "Contact Form Demo" to duplicate — is Fluent Forms freshly installed?')

    dup = wp.post(f'fluentform/v1/forms/{demo["id"]}/duplicate', {})
    form_id = dup['form_id']

    built = []
    for index, (kind, name, label, placeholder, required) in enumerate(fields):
        field = FIELD_TEMPLATES[kind](name, label, placeholder, required)
        field['index'] = index
        field['uniqElKey'] = f'el_{name}'
        built.append(field)

    payload = {
        'fields': built,
        'submitButton': {
            'uniqElKey': 'el_submit', 'element': 'button',
            'attributes': {'type': 'submit', 'class': ''},
            'settings': {'container_class': '', 'align': 'left', 'button_style': '',
                         'button_size': 'md',
                         'button_ui': {'type': 'default', 'text': submit_text, 'img_url': ''},
                         'normal_styles': {}, 'hover_styles': {}, 'current_state': 'normal_styles'},
            'editor_options': {'title': 'Submit Button'},
        },
    }
    wp.post(f'fluentform/v1/forms/{form_id}', {'title': title, 'form_fields': json.dumps(payload)})
    print(f'form {form_id} created: {title}')
    print(f'embed with:  [fluentform id="{form_id}"]')
    print('wrap the embed in a container with the gt-form-card class to inherit brand styling')
    return form_id


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


def emails(form_id, to_address, business='Our Shop', logo_url='', address='', hours='',
           phone='', collection_url=''):
    """Brand the on-page confirmation, the admin notification, and the client auto-reply."""
    wp = WP()

    # --- on-page confirmation -------------------------------------------------
    settings_rows = wp.ff_settings(form_id, 'formSettings')
    row = settings_rows[0]
    form_settings = row['value']
    form_settings['confirmation']['messageToShow'] = (
        '<div style="text-align:center;padding:0.5rem 0">'
        '<div style="font-size:26px;line-height:1.2;margin-bottom:8px;'
        'font-family:var(--gt-font-heading,Georgia,serif);color:var(--gt-ink,#33291f);'
        'font-weight:600">Thank you — message received</div>'
        '<div style="color:var(--gt-muted,#6e6456);font-size:15px">We will get back to you '
        f'within a day or two.{f" Need us sooner? Call {phone}." if phone else ""}</div></div>')
    # meta_id is REQUIRED to update in place — without it Fluent Forms inserts a duplicate row
    wp.ff_save_setting(form_id, 'formSettings', form_settings, meta_id=row['id'])
    print('confirmation message updated')

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
        + row_html('Name', '{inputs.name}')
        + row_html('Phone', '{inputs.phone}')
        + row_html('Email', '<a href="mailto:{inputs.email}" style="color:#7e5aa6">{inputs.email}</a>')
        + row_html('Message', '{inputs.message}')
        + '</table>'
        '<p style="font-family:Arial,sans-serif;font-size:13px;color:#6e6456;margin:20px 0 0">'
        'Reply directly to this email to answer {inputs.name}.</p>')

    cta = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto">'
           f'<tr><td style="border-radius:12px;background-color:#7e5aa6" align="center">'
           f'<a href="{collection_url}" style="display:inline-block;padding:13px 28px;'
           f'font-family:Arial,sans-serif;font-size:14px;color:#fbf6ec;text-decoration:none">'
           f'Browse the Collection</a></td></tr></table>') if collection_url else ''

    client_inner = (
        '<h2 style="font-family:Georgia,serif;font-weight:600;font-size:24px;margin:0 0 6px;'
        'color:#33291f">We got your message</h2>'
        '<p style="font-family:Arial,sans-serif;font-size:14px;color:#33291f;line-height:1.6;'
        'margin:0 0 16px">Hi {inputs.name},</p>'
        '<p style="font-family:Arial,sans-serif;font-size:14px;color:#33291f;line-height:1.6;'
        f'margin:0 0 16px">Thanks for reaching out to {business} — your note landed safely and '
        'we will get back to you within a day or two.</p>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background-color:#f2e8d6;border-radius:12px;padding:8px;margin:0 0 20px">'
        + row_html('You wrote', '{inputs.message}') + '</table>' + cta)

    existing = {n['value'].get('name'): n for n in wp.ff_settings(form_id, 'notifications')}

    admin = {
        'name': 'Admin Notification',
        'sendTo': {'type': 'email', 'email': to_address, 'field': '', 'routing': []},
        'fromName': f'{business} Website', 'fromEmail': to_address,
        'replyTo': '{inputs.email}', 'bcc': '',
        'subject': 'New message from {inputs.name}',
        'message': _email_shell(admin_inner, 'New contact form message from {inputs.name}',
                                logo_url, business, address, hours),
        'conditionals': {'status': False, 'type': 'all', 'conditions': []},
        'enabled': True, 'email_template': '',
    }
    wp.ff_save_setting(form_id, 'notifications', admin,
                       meta_id=existing.get('Admin Notification', {}).get('id'))
    print('admin notification ->', to_address)

    client = {
        'name': 'Client Confirmation',
        'sendTo': {'type': 'field', 'email': '', 'field': 'email', 'routing': []},
        'fromName': business, 'fromEmail': to_address, 'replyTo': to_address, 'bcc': '',
        'subject': f'We got your message — {business}',
        'message': _email_shell(client_inner, 'Thanks {inputs.name} — we will be in touch',
                                logo_url, business, address, hours),
        'conditionals': {'status': False, 'type': 'all', 'conditions': []},
        'enabled': True, 'email_template': '',
    }
    wp.ff_save_setting(form_id, 'notifications', client,
                       meta_id=existing.get('Client Confirmation', {}).get('id'))
    print('client confirmation -> submitter')

    rows = wp.ff_settings(form_id, 'notifications')
    print('notifications now:', [(r['id'], r['value']['name']) for r in rows])
    if len({r['value']['name'] for r in rows}) != len(rows):
        print('WARNING: duplicate notification rows — pass meta_id when updating.')


def seo(descriptions=None):
    """
    Stage meta descriptions. Rank Math does not expose rank_math_* meta over REST until
    its wizard has run, but its default template falls back to the excerpt, which is a
    first-class REST field — so writing excerpts works before or after the wizard.
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
        emails(sys.argv[2], sys.argv[3])
    elif command == 'seo':
        seo()
    else:
        print(__doc__)
