{
    'name': 'Product',
    'version': '1.0',
    'summary': """ Product """,
    'description': """ Product """,
    'author': 'Planet-Odoo',
    'license': 'AGPL-3',
    'website': 'https://planet-odoo.com/',
    'category': '',
    'depends': ['product', 'account', 'l10n_in', 'stock_account', 'mail', 'stock', 'base'],
    'data': [
        'security/ir.model.access.csv',
        'security/security_view.xml',
        'wizard/views/approve_product.xml',
        'views/product_view.xml',
        'views/restrict_product_create.xml',
        'wizard/views/update_product_cost.xml',
        # 'views/cost_cron.xml',
        'template/email_template.xml',
        'wizard/views/import_quantity.xml',
    ],

    'installable': True,
    'application': True,
}
