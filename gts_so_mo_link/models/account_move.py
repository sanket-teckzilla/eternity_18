from odoo import api, fields, models, exceptions, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    partner_billing_id = fields.Many2one('res.partner',string="Billing Address")






