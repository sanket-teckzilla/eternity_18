{
    'name': 'Purchase',
    'version': '1.0',
    'summary': """ Purchase """,
    'description': """ Purchase """,
    'author': 'GeoTechnosoft',
    'license': 'AGPL-3',
    'website': 'http://www.geotechnosoft.com',
    'category': '',
    'depends': ['base', 'purchase','l10n_in_purchase','stock','product','report_custom_layout'],
    'data': [
        'report/report_purchase_order_inherit.xml',
        'report/report_purchase_quotation_inherit.xml',
        'views/purchase_view.xml',

    ],
    'installable': True,
    'application': True,
}
