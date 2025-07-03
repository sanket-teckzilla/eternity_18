{
    'name': 'CRM',
    'version': '1.0',
    'summary': """ CRM """,
    'description': """ CRM """,
    'author': 'GeoTechnosoft',
    'license': 'AGPL-3',
    'website': 'http://www.geotechnosoft.com',
    'category': '',
    'depends': ['base', 'crm'],
    'data': [
        'security/security_view.xml',
        'views/crm_view.xml',
    ],

    'installable': True,
    'application': True,
}
