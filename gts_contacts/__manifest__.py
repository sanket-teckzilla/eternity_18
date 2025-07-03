{
    'name': 'Contacts',
    'version': '1.0',
    'summary': """ Contacts """,
    'description': """ Contacts """,
    'author': 'Planet Odoo',
    'license': 'AGPL-3',
    'website': 'http://www.geotechnosoft.com',
    'category': '',
    'depends': ['base', 'contacts', 'sales_team', 'account', 'base_vat'],
    'data': [
        'security/security_view.xml',
        'security/ir.model.access.csv',
        'views/res_partner_view.xml',
        'views/restrict_create.xml',
        'views/country_view.xml',
        'data/cron.xml'
    ],

    'installable': True,
    'application': True,
}
