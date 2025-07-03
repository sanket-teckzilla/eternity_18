from odoo import models, api, fields, _
import base64
from odoo.exceptions import UserError


class PriceApproval(models.TransientModel):
    _name = 'price.approval'
    _description = 'price approval'

    @api.model
    def default_get(self, fields_list):
        res = super(PriceApproval, self).default_get(fields_list)
        res['sale_id'] = self.env.context['active_id']
        sale = self.env['sale.order'].browse(self.env.context['active_id'])
        res['customer'] = sale.partner_id.id
        res['payment_term'] = sale.payment_term_id.id

        return res

    # def default_sale(self):
    #     sale_id = self.env.context['active_id']
    #     return sale_id


    sale_id = fields.Many2one('sale.order')
    date = fields.Date("Date")
    customer = fields.Many2one('res.partner',string="Customer")
    battery_rating_cell_type = fields.Char("Battery Rating with Cell Type")
    drawing_no = fields.Char("ET Drawing No.")
    currency_id = fields.Many2one('res.currency', 'Currency', required=True,
                                  default=lambda self: self.env.company.currency_id.id)
    price_req = fields.Monetary("Price Required")
    validity = fields.Date("Validity")
    transportation = fields.Char("Transportation")
    payment_term = fields.Many2one('account.payment.term',"Payment Term")
    justification = fields.Text("Justification")


    def send_price_request(self):
        report_template_id = self.env.ref('gts_sale.action_report_price_request')._render_qweb_pdf(self.id)
        data_record = base64.b64encode(report_template_id[0])
        ir_values = {
            'name': 'Price Request - %s' % (self.sale_id.name),
            'type': 'binary',
            'datas': data_record,
            'store_fname': data_record,
            'mimetype': 'application/x-pdf',
        }
        data_id = self.env['ir.attachment'].create(ir_values)

        self.sale_id.write({'state': 'sent_for_approval'})
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        template_id = self.env.ref('gts_sale.quotation_sent_for_approval')
        action_id = self.env.ref('gts_sale.action_pending_for_approval').id
        params = str(base_url) + "/web#id=%s&view_type=form&model=sale.order&action=%s" % (
            self.sale_id.id, action_id
        )
        sales_url = str(params)
        users_list = self.env['res.users'].search([])
        email_to, email_from = '', ''
        for group_user in users_list:
            if group_user.has_group('gts_sale.quotation_approval'):
                email_to += group_user.login
        email_from = self.env.user.login + ' ,' + 'odoo@eternitytechnologies.com'
        if template_id:
            values = template_id.generate_mail(self.sale_id.id,
                                                ['subject', 'body_html', 'email_from', 'email_to', 'partner_to',
                                                 'email_cc', 'reply_to', 'scheduled_date'])
            values['email_to'] = 'nitin.planetodoo@gmail.com'
            values['email_from'] = email_from
            values['reply_to'] = self.env.user.login
            values['body_html'] = values['body_html'].replace('_sales_url', sales_url)
            values['attachment_ids'] = [(6, 0, data_id.ids)]
            mail = self.env['mail.mail'].sudo().create(values)
            try:
                mail.send()
            except Exception:
                pass