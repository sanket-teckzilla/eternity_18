{
    'name': 'Account',
    'version': '1.0',
    'summary': """ Account """,
    'description': """ Account """,
    'author': 'GeoTechnosoft',
    'license': 'AGPL-3',
    'website': 'http://www.geotechnosoft.com',
    'category': '',
    # 'depends': ['base', 'account', 'gts_contacts','report_custom_layout', 'sale', 'web', 'sale_stock','l10n_in','gts_so_mo_link','],
    'depends': ['base', 'account', 'gts_contacts','report_custom_layout', 'sale', 'web', 'sale_stock','l10n_in','gts_so_mo_link','l10n_in_edi_ewaybill','account_reports','account_followup','account_bank_statement_extract'],
    'data': [
        'security/ir.model.access.csv',
        'security/security_view.xml',
        'views/invoice_form_view.xml',
        'views/account_move_line.xml',
        'views/tds_report.xml',
        'report/external_layout.xml',
        'report/report_invoice_eternity.xml',
        'report/report_invoice_inherit.xml',
        'report/report_view.xml',
        'report/payment_receipt.xml',
        'views/account_account_views.xml',
        'wizard/ageing_report.xml',
        # 'report/report_invoice_sr_number.xml'
        "report/l10n_invoice_inher.xml",

        "report/l10n_in_edi_inherit_rem.xml"
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
