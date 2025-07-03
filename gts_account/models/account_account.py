from odoo import models, api, _, fields
from datetime import datetime, date


class AccountAccount(models.Model):
    _inherit = 'account.account'

    is_tds_ledger = fields.Boolean("Is TDS Ledger")




class AccountMove(models.Model):
    # _name = 'account.move'
    _inherit = 'account.move'

    transportation_mode = fields.Selection([('1', 'Road'),
                                            ('2', 'Rail'),
                                            ('3', 'Air'),
                                            ('4', 'Ship'),
                                            ], string="Transportation Mode")
    transporter_id = fields.Many2one('res.partner', string="Transporter", tracking=2)
    transporter_doc_no = fields.Char("Transporter Document No.", size=16, tracking=2)
    transportation_doc_date = fields.Date('Transport Document Date', tracking=2)
    trans_id = fields.Char("Transporter ID", tracking=2)
    vehicle_type = fields.Selection([('R', 'Regular'),
                                     ('O', 'ODC')], string="Vechicle Type", tracking=2)
    vehicle_no = fields.Char("Vehicle No", tracking=2)
    gst_status = fields.Selection([
        ('not_uploaded', 'Not Uploaded'),
        ('ready_to_upload', 'Ready to upload'),
        ('uploaded', 'Uploaded to govt'),
        ('filed', 'Filed')
    ],
        string='GST Status',
        default="not_uploaded",
        copy=False,
        help="status will be consider during gst import, "
    )
    invoice_type = fields.Selection([
        ('b2b', 'B2B'),
        ('b2cl', 'B2CL'),
        ('b2cs', 'B2CS'),
        ('b2bur', 'B2BUR'),
        ('import', 'IMPS/IMPG'),
        ('export', 'Export'),
        ('cdnr', 'CDNR'),
        ('cdnur', 'CDNUR'),
    ],
        copy=False,
        string='Invoice Type'
    )
    export = fields.Selection([
        ('WPAY', 'WPay'),
        ('WOPAY', 'WoPay')
    ],
        string='Export'
    )
    export_type = fields.Selection([
        ('regular', 'Regular'),
        ('sez_with_payment', 'SEZ supplies with payment'),
        ('sez_without_payment', 'SEZ supplies without payment'),
        ('deemed', 'Deemed Exp'),
        ('intra_state_igst', 'Intra-State supplies attracting IGST'),
    ],
        string='Export Type',
        default='regular',
        required=True
    )
    itc_eligibility = fields.Selection([
        ('Inputs', 'Inputs'),
        ('Capital goods', 'Capital goods'),
        ('Input services', 'Input services'),
        ('Ineligible', 'Ineligible'),
    ],
        string='ITC Eligibility',
        default='Ineligible'
    )
    reverse_charge = fields.Boolean(
        string='Reverse Charge',
        help="Allow reverse charges for b2b invoices")




    def get_fiscal_year_start_date(self, company, invoice_date):
        fiscal_year_start_month = (int(company.fiscalyear_last_month) % 12) + 1
        fiscal_year_start_date = date(invoice_date.year, fiscal_year_start_month, 1)
        if invoice_date.month <= 11:
            fiscal_year_start_date = fiscal_year_start_date.replace(year=invoice_date.year - 1)
        return fiscal_year_start_date

