from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleModify(models.Model):
    _name = "sale.modify"
    _description = "sale modify"

    comment = fields.Text('Comments')
    sale_id = fields.Many2one('sale.order', 'Sale Order')

    @api.model
    def default_get(self, fields):
        res = super(SaleModify, self).default_get(fields)
        context = self._context
        active_id = context.get('active_id')
        res['sale_id'] = active_id
        return res

    def request_to_modify(self):
        context = self._context
        current_uid = context.get('uid')
        active_id = self.env['sale.order'].browse(self._context['active_id'])
        active_id.write({'state': 'draft',
                         'modify_history_bool': True,
                         'modify_comments': self.comment})
        dict = {
            'sale_id': active_id.id,
            'requested_by': self.env.user.id,
            'request_date': fields.Datetime.now(),
            'comment': self.comment
        }
        self.env['sale.modify.history'].create(dict)
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        template_id = self.env.ref('gts_sale.quotation_request_to_modify')
        action_id = self.env.ref('sale.action_quotations_with_onboarding').id
        params = str(base_url) + "/web#id=%s&view_type=form&model=sale.order&action=%s" % (
            self.sale_id.id, action_id
        )
        sales_url = str(params)
        email_from = self.env.user.name + ' ,' + 'odoo@eternitytechnologies.com'
        if template_id:
            values = template_id.generate_email(self.id, ['subject', 'body_html', 'email_from', 'email_to', 'partner_to', 'email_cc', 'reply_to', 'scheduled_date'])
            values['email_to'] = active_id.user_id.partner_id.email or active_id.create_uid.partner_id.id
            values['email_from'] = email_from
            values['reply_to'] = self.env.user.partner_id.email
            values['body_html'] = values['body_html'].replace('_sales_url', sales_url)
            mail = self.env['mail.mail'].sudo().create(values)
            active_id.message_post(
                body=values['body_html'],
                subtype_xmlid='mail.mt_comment',
                notif_layout='mail.mail_notification_light',
            )
            try:
                mail.send()
            except Exception:
                pass
