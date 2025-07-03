from odoo import _, api, fields, models, SUPERUSER_ID, tools
import base64


class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    attach_design = fields.Boolean('Attach Design', default=False)
    show_design = fields.Boolean('Show Design', default=False, )

    @api.model
    def default_get(self, fields):
        rec = super(MailComposer, self).default_get(fields)
        active_model = self.env.context.get('active_model')
        if active_model == 'sale.order':
            show_design = False
            sale_order = self.env['sale.order'].search([('id', '=', self.env.context.get('active_id'))], limit=1)
            for lines in sale_order.order_line:
                if lines.product_id.product_tmpl_id.pdf_attachment_id.datas:
                    show_design = True
            rec.update({'show_design': show_design})
        return rec

    @api.onchange('attach_design')
    def _onchange_attach_design(self):
        if self.model == 'sale.order' and self.id:
            sale_order = self.env['sale.order'].search([('id', '=', self.res_id)], limit=1)
            x = 0
            attachment_list = []
            for rec in self.attachment_ids:
                if x == 0:
                    x += 1
                    attachment_list = [rec]
            if sale_order and self.attach_design:
                for lines in sale_order.order_line:
                    pdf_attachment = lines.product_id.product_tmpl_id.pdf_attachment_id.datas
                    if pdf_attachment:
                        attach_datas = {
                            'name': lines.product_id.product_tmpl_id.attach_design_pdf_filename,
                            'datas': pdf_attachment,
                            # 'datas_fname': lines.product_id.product_tmpl_id.attach_design_pdf_filename,
                            'res_model': 'mail.compose.message',
                            'res_id': 0,
                            'type': 'binary',
                        }
                        attachment = self.env['ir.attachment'].create(attach_datas)
                        attachment_list.append(attachment)
                self.attachment_ids = [(6, 0, [rec.id for rec in attachment_list])]
            elif sale_order and not self.attach_design:
                self.attachment_ids = [(6, 0, [rec.id for rec in attachment_list])]

    def get_mail_values(self, res_ids):
        """Generate the values that will be used by send_mail to create mail_messages
        or mail_mails. """
        self.ensure_one()
        results = dict.fromkeys(res_ids, False)
        rendered_values = {}
        mass_mail_mode = self.composition_mode == 'mass_mail'

        # render all template-based value at once
        if mass_mail_mode and self.model:
            rendered_values = self.render_message(res_ids)
        # compute alias-based reply-to in batch
        reply_to_value = dict.fromkeys(res_ids, None)
        if mass_mail_mode and not self.no_auto_thread:
            records = self.env[self.model].browse(res_ids)
            reply_to_value = records._notify_get_reply_to(default=self.email_from)

        blacklisted_rec_ids = set()
        if mass_mail_mode and issubclass(type(self.env[self.model]), self.pool['mail.thread.blacklist']):
            self.env['mail.blacklist'].flush(['email'])
            self._cr.execute("SELECT email FROM mail_blacklist")
            blacklist = {x[0] for x in self._cr.fetchall()}
            if blacklist:
                targets = self.env[self.model].browse(res_ids).read(['email_normalized'])
                # First extract email from recipient before comparing with blacklist
                blacklisted_rec_ids.update(target['id'] for target in targets
                                           if target['email_normalized'] in blacklist)

        for res_id in res_ids:
            # static wizard (mail.message) values
            mail_values = {
                'subject': self.subject,
                'body': self.body or '',
                'parent_id': self.parent_id and self.parent_id.id,
                'partner_ids': [partner.id for partner in self.partner_ids],
                'attachment_ids': [attach.id for attach in self.attachment_ids],
                'author_id': self.author_id.id,
                'email_from': self.email_from,
                'reply_to': self.env.user.email,
                'record_name': self.record_name,
                'no_auto_thread': self.no_auto_thread,
                'mail_server_id': self.mail_server_id.id,
                'mail_activity_type_id': self.mail_activity_type_id.id,
            }

            # mass mailing: rendering override wizard static values
            if mass_mail_mode and self.model:
                record = self.env[self.model].browse(res_id)
                mail_values['headers'] = record._notify_email_headers()
                # keep a copy unless specifically requested, reset record name (avoid browsing records)
                mail_values.update(notification=not self.auto_delete_message, model=self.model, res_id=res_id,
                                   record_name=False)
                # auto deletion of mail_mail
                if self.auto_delete or self.template_id.auto_delete:
                    mail_values['auto_delete'] = True
                # rendered values using template
                email_dict = rendered_values[res_id]
                mail_values['partner_ids'] += email_dict.pop('partner_ids', [])
                mail_values.update(email_dict)
                if not self.no_auto_thread:
                    mail_values.pop('reply_to')
                    if reply_to_value.get(res_id):
                        mail_values['reply_to'] = reply_to_value[res_id]
                if self.no_auto_thread and not mail_values.get('reply_to'):
                    mail_values['reply_to'] = mail_values['email_from']
                # mail_mail values: body -> body_html, partner_ids -> recipient_ids
                mail_values['body_html'] = mail_values.get('body', '')
                mail_values['recipient_ids'] = [(4, id) for id in mail_values.pop('partner_ids', [])]

                # process attachments: should not be encoded before being processed by message_post / mail_mail create
                mail_values['attachments'] = [(name, base64.b64decode(enc_cont)) for name, enc_cont in
                                              email_dict.pop('attachments', list())]
                attachment_ids = []
                for attach_id in mail_values.pop('attachment_ids'):
                    new_attach_id = self.env['ir.attachment'].browse(attach_id).copy(
                        {'res_model': self._name, 'res_id': self.id})
                    attachment_ids.append(new_attach_id.id)
                attachment_ids.reverse()
                mail_values['attachment_ids'] = self.env['mail.thread']._message_post_process_attachments(
                    mail_values.pop('attachments', []),
                    attachment_ids,
                    {'model': 'mail.message', 'res_id': 0}
                )['attachment_ids']
                # Filter out the blacklisted records by setting the mail state to cancel -> Used for Mass Mailing stats
                if res_id in blacklisted_rec_ids:
                    mail_values['state'] = 'cancel'
                    # Do not post the mail into the recipient's chatter
                    mail_values['notification'] = False

            results[res_id] = mail_values
        return results