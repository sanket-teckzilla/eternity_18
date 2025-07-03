{
    'name': 'PO Daily Report',
    'version': '1.0',
    'sequence': 1,
    'description': '',
    'author': 'Planet Odoo',
    'depends': ['base', 'account', 'sale', 'purchase', 'gts_account',
                'account_reports', 'stock_account'],
    'data': [
        'reports/report.xml',
        # 'reports/template.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
    'license': 'OEEL-1',
}
