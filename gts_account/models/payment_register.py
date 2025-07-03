from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class PaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'


    payment_method_code = fields.Char(
        related='payment_method_line_id.code')
    suitable_payment_token_partner_ids = fields.Many2many(
        comodel_name='res.partner',
        compute='_compute_suitable_payment_token_partner_ids')
    payment_token_id = fields.Many2one(
        comodel_name='payment.token',
        string="Saved payment token",
        store=True, readonly=False,
        compute='_compute_payment_token_id',
        domain='''[
                (payment_method_code == 'electronic', '=', 1),
                ('company_id', '=', company_id),
                ('acquirer_id.capture_manually', '=', False),
                ('acquirer_id.journal_id', '=', journal_id),
                ('partner_id', 'in', suitable_payment_token_partner_ids),
            ]''',
        help="Note that tokens from acquirers set to only authorize transactions (instead of capturing the amount) are "
             "not available.")

    @api.onchange('can_edit_wizard', 'payment_method_line_id', 'journal_id')
    def _compute_payment_token_id(self):
        for wizard in self:
            if wizard.can_edit_wizard \
                    and wizard.payment_method_line_id.code == 'electronic' \
                    and wizard.journal_id \
                    and wizard.suitable_payment_token_partner_ids:
                wizard.payment_token_id = self.env['payment.token'].search([
                    ('partner_id', 'in', wizard.suitable_payment_token_partner_ids.ids),
                    ('acquirer_id.capture_manually', '=', False),
                    ('acquirer_id.journal_id', '=', wizard.journal_id.id),
                ], limit=1)
            else:
                wizard.payment_token_id = False


    @api.depends('can_edit_wizard')
    # changes in function for migration
    # def _compute_suitable_payment_token_partner_ids(self):
    #     for wizard in self:
    #         if wizard.can_edit_wizard:
    #             lines = wizard._compute_batches()[0]['lines']
    #             partners = lines.partner_id
    #             commercial_partners = partners.commercial_partner_id
    #             children_partners = commercial_partners.child_ids
    #             wizard.suitable_payment_token_partner_ids = (partners + commercial_partners + children_partners)._origin
    #         else:
    #             wizard.suitable_payment_token_partner_ids = False

    def _compute_suitable_payment_token_partner_ids(self):
        for wizard in self:
            if wizard.can_edit_wizard:
                batches = wizard._compute_batches()
                if batches and isinstance(batches, list) and len(batches) > 0:
                    lines = batches[0].get('lines', [])
                    if lines:
                        partners = lines.partner_id
                        commercial_partners = partners.commercial_partner_id
                        children_partners = commercial_partners.child_ids
                        wizard.suitable_payment_token_partner_ids = (
                                    partners + commercial_partners + children_partners)._origin
                    else:
                        wizard.suitable_payment_token_partner_ids = False
                else:
                    wizard.suitable_payment_token_partner_ids = False
            else:
                wizard.suitable_payment_token_partner_ids = False


class AccountStatment(models.Model):
    _inherit = 'account.bank.statement'

    country_code = fields.Char(related='company_id.country_id.code')

