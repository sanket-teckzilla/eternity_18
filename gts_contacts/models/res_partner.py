from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_company = fields.Boolean(string='Is a Company', default=True,
                                help="Check if the contact is a company, otherwise it is a person")
    pan = fields.Char(string="PAN", size=10)
    region_id = fields.Many2one('res.country.region', 'Region', related='state_id.region_id', store=True)
    partner_company_registry_placeholder = fields.Char('Partner Company Registry Placeholder')

    # added below field and function for migration

    partner_type = fields.Selection([('B2B', 'B2B'), ('B2BUR', 'B2BUR'), ('IMPORT', 'IMPS/IMPG')],
                                    string='Partner Type', copy=False,
                                    compute='_compute_partner_type',
                                    help="""
                                            * B2B : B2B Supplies.
                                            * B2BUR : Inward supplies from unregistered Supplier.
                                            * IMPORT : Import of Services/Goods.
                                        """)

    transporter = fields.Boolean("Is Transporter?", tracking=2)

    @api.depends('vat')
    def _compute_partner_type(self):
        if self.country_id.code == 'IN':
            if self.vat:
                self.partner_type = 'B2B'
            else:
                self.partner_type = 'B2BUR'
        else:
            self.partner_type = 'IMPORT'


    @api.onchange('pan')
    def onchange_pan(self):
        if self.supplier_rank and self.pan:
            if len(self.pan) < 10:
                self.pan = ''
                raise UserError(
                    _('PAN Number %s should be 10 digits' % self.pan))

    @api.model
    def default_get(self, fields):
        rec = super(ResPartner, self).default_get(fields)
        country = self.env['res.country'].search([('code', '=', 'IN')], limit=1)
        if country:
            rec['country_id'] = country.id
        return rec

    @api.constrains('pan')
    def check_vat(self):
        for record in self:
            if record.l10n_in_pan:
                if len(record.l10n_in_pan < 10):
                    raise ValidationError('The PAN no cannot be greater than 10 digit !')

    # Function to run cron job to send Mails to Salesperson for their customer overdue --CJ
    def _cron_execute_followup_salesperson(self):
        followup_data = self._query_followup_level(all_partners=True)
        in_need_of_action = self.env['res.partner'].browse([d['partner_id'] for d in followup_data.values() if d['followup_status'] == 'in_need_of_action'])
        for partner in in_need_of_action:
            try:
                if partner.user_id:
                    partner._execute_followup_partner_salesperson()
            except UserError as e:
                # followup may raise exception due to configuration issues
                # i.e. partner missing email
                _logger.exception(e)

    def _execute_followup_partner_salesperson(self):
        self.ensure_one()
        if self.followup_status == 'in_need_of_action':
            followup_line = self.followup_level
            if followup_line.send_email:
                self.send_followup_email_to_salesperson()
            if followup_line.manual_action:
                # log a next activity for today
                self.activity_schedule(
                    activity_type_id=followup_line.manual_action_type_id and followup_line.manual_action_type_id.id or self._default_activity_type().id,
                    summary=followup_line.manual_action_note,
                    user_id=(followup_line.manual_action_responsible_id and followup_line.manual_action_responsible_id.id) or self.env.user.id
                )
            if followup_line.print_letter:
                return self
        return None

    def send_followup_email_to_salesperson(self):
        """
        Send a follow-up report by email to salesperson in self
        """
        for record in self:
            options = {
                'partner_id': record.id,
                'sales_person': record.user_id.partner_id,
            }
            self.env['account.followup.report'].send_mail_to_salesperson(options)


