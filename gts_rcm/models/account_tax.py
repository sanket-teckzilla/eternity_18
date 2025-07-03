from odoo import api, fields, models, _
from odoo import exceptions
from odoo.exceptions import UserError, ValidationError


class AccountTax(models.Model):
    _inherit = "account.tax"

    account_id = fields.Many2one('account.account', string='RCM Account')

    @api.onchange('l10n_in_reverse_charge')
    def onchange_l10n_in_reverse_charge(self):
        if self.l10n_in_reverse_charge is False:
            self.account_id = ''
