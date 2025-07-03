from odoo import api, fields, tools, models, _
from odoo import exceptions
from odoo.exceptions import UserError, ValidationError
from num2words import num2words
from datetime import datetime,date, timedelta
from dateutil.relativedelta import relativedelta


class WarrantyPeriod(models.Model):
    _name = "warranty.period"
    _description = "warranty period"

    partner_id = fields.Many2one('res.partner', string='Partner')
    battery_no = fields.Many2one('product.product', string='Battery No.')
    cell_type = fields.Many2one('product.product', string='Cell Type')
    battery_sr_no = fields.Char(string='Battery Sr No.')
    cell_sr_no = fields.Char('Cell Sr No.(Lot)')
    invoice_ref = fields.Many2one('account.move', string='Invoice Reference')
    picking_id = fields.Many2one('stock.picking', string='Picking')
    validity_from = fields.Date('Validity From')
    validity_to = fields.Date('Validity To')
    quantity = fields.Float('Quantity')
