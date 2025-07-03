import re

from odoo import models, api, _, fields
from datetime import datetime
from odoo.exceptions import ValidationError


class PickDate(models.TransientModel):
    _name = 'tds.dateselector'
    _description = 'tds dateselector'

    start_date = fields.Date(string="Start Date")
    end_date = fields.Date(string="End Date")

    @api.onchange('start_date', 'end_date')
    def date_validator(self):
        current_date = datetime.now().date()
        if self.start_date and self.start_date > current_date:
            raise ValidationError('Start date should not be of future')
        elif self.end_date and self.end_date > current_date:
            raise ValidationError('End date should not be of future')
        elif self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError('Start date should be smaller then end date.')

    def generate_tds_report(self):
        self.env.cr.execute("""Delete from tds_report_wizard""")
        domain = [('date', '>=', self.start_date), ('date', '<=', self.end_date),
                  ('display_type', 'not in', ('line_section', 'line_note')),('account_id.is_tds_ledger','=',True)]
        # move_lines = self.env['account.move.line'].search(domain).filtered(
        #     lambda x: (x.account_id.name and re.search(r'\btds\b', x.account_id.name, flags=re.IGNORECASE)))
        move_lines = self.env['account.move.line'].search(domain)
        data = dict()
        for line in move_lines:
            move_id = line.move_id.id
            if data.get(move_id) is None:
                data.update({move_id: {"debit": line.debit, 'credit': line.credit, "balance": line.balance,
                                       "amount_currency": line.amount_currency, "move_id": move_id, 'name': line.name,
                                       "account_id": line.account_id.id, "account_code": line.account_id.code,
                                       "account_name": line.account_id.name}})
            else:
                data[move_id]["debit"] += line.debit or 0
                data[move_id]["credit"] += line.credit or 0
                data[move_id]["balance"] += line.balance or 0

        self.env['tds.report.wizard'].create(data.values())
        return {
            'name': _('TDS Report'),
            'view_mode': 'list',
            'res_model': 'tds.report.wizard',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'main',
        }


class TDSReportWizard(models.TransientModel):
    _name = 'tds.report.wizard'
    _description = 'tds report wizard'

    move_id = fields.Many2one('account.move', string='Journal Entry', index=True, auto_join=True, ondelete="cascade",
                              help="The move of this entry line.")
    company_id = fields.Many2one(related='move_id.company_id', store=True, readonly=True,
                                 default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Company Currency',
                                          readonly=True, store=True,
                                          help='Utility field to express amount currency')
    debit = fields.Monetary(string='Debit', default=0.0, currency_field='company_currency_id')
    credit = fields.Monetary(string='Credit', default=0.0, currency_field='company_currency_id')
    balance = fields.Monetary(string='Balance', currency_field='company_currency_id')
    amount_currency = fields.Monetary(string='Amount in Currency', currency_field='company_currency_id')
    cumulated_balance = fields.Monetary(string='Cumulated Balance', currency_field='company_currency_id')
    name = fields.Char(string='Label', related='move_id.name')
    date = fields.Date(related='move_id.date', store=True, readonly=True, index=True, copy=False, group_operator='min')
    ref = fields.Char(related='move_id.ref', store=True, copy=False, index=True, readonly=False)
    account_id = fields.Many2one('account.account', string='Account', index=True, ondelete="cascade", tracking=True)
    account_code = fields.Char(string="Account Code")
    account_name = fields.Char(string="Account Name")
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete="cascade", related='move_id.partner_id')
    pan_num = fields.Char(string="Pancard", related="partner_id.pan")
    untaxed_amount = fields.Monetary(string="Untaxed Amount",currency_field='company_currency_id', related='move_id.amount_untaxed')

    @api.model_create_multi
    def create(self, values):
        return super(TDSReportWizard, self).create(values)
