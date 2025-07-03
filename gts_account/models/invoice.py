import datetime
import operator
from collections import defaultdict
from odoo import api, fields, models, _
from odoo.tools import float_is_zero
from odoo.exceptions import ValidationError
from babel.numbers import format_currency




class AccountInvoice(models.Model):
    # _name = "account.move"
    _inherit = "account.move"

    po_number = fields.Char(string="PO Number")
    billing_city = fields.Char(related='partner_billing_id.city', string="Billing City")

    # Cj: Using this Function to retrieve tds amount for Vendor Payment Receipt
    # def _get_tds_amt(self):
    #     tax_line = self.amount_by_group
    #     for line in tax_line:
    #         if 'tds' in line[0].lower():
    #             return float("{:.2f}".format(abs(line[1])))
    #     return 0

    def _get_tds_amt(self):
        self.ensure_one()
        tax_totals = self.tax_totals
        tds_amount = 0.0
        for subtotal in tax_totals.get('groups_by_subtotal', {}).get('Untaxed Amount', []):
            if 'tds' in subtotal.get('tax_group_name', '').lower():
                tds_amount += subtotal.get('tax_group_amount', 0.0)
        return tds_amount


    @api.onchange('partner_id')
    def update_fiscal_position(self):
        company = self.env.company
        if self.partner_id:
            if self.partner_id.state_id == company.state_id:
                self.fiscal_position_id = False
            else:
                interstate = self.env['account.fiscal.position'].search([('name','=','Inter State')])
                self.fiscal_position_id = interstate.id

    @api.depends('posted_before', 'state', 'journal_id', 'date')
    def _compute_name(self):
        for move in self:
            if move.state == 'posted':
                def journal_key(move):
                    return (move.journal_id, move.journal_id.refund_sequence and move.move_type)

                def date_key(move):
                    return (move.date.year, move.date.month)

                grouped = defaultdict(  # key: journal_id, move_type
                    lambda: defaultdict(  # key: first adjacent (date.year, date.month)
                        lambda: {
                            'records': self.env['account.move'],
                            'format': False,
                            'format_values': False,
                            'reset': False
                        }
                    )
                )
                self = self.sorted(lambda m: (m.date, m.ref or '', m.id))
                highest_name = self[0]._get_last_sequence() if self else False

                # Group the moves by journal and month
                for move in self:
                    if not highest_name and move == self[0] and not move.posted_before and move.date:
                        # In the form view, we need to compute a default sequence so that the user can edit
                        # it. We only check the first move as an approximation (enough for new in form view)
                        pass
                    elif (move.name and move.name != '/') or move.state != 'posted':
                        try:
                            if not move.posted_before:
                                move._constrains_date_sequence()
                            # Has already a name or is not posted, we don't add to a batch
                            continue
                        except ValidationError:
                            # Has never been posted and the name doesn't match the date: recompute it
                            pass
                    group = grouped[journal_key(move)][date_key(move)]
                    if not group['records']:
                        # Compute all the values needed to sequence this whole group
                        move._set_next_sequence()
                        group['format'], group['format_values'] = move._get_sequence_format_param(move.name)
                        group['reset'] = move._deduce_sequence_number_reset(move.name)
                    group['records'] += move

                # Fusion the groups depending on the sequence reset and the format used because `seq` is
                # the same counter for multiple groups that might be spread in multiple months.
                final_batches = []
                for journal_group in grouped.values():
                    journal_group_changed = True
                    for date_group in journal_group.values():
                        if (
                                journal_group_changed
                                or final_batches[-1]['format'] != date_group['format']
                                or dict(final_batches[-1]['format_values'], seq=0) != dict(date_group['format_values'], seq=0)
                        ):
                            final_batches += [date_group]
                            journal_group_changed = False
                        elif date_group['reset'] == 'never':
                            final_batches[-1]['records'] += date_group['records']
                        elif (
                                date_group['reset'] == 'year'
                                and final_batches[-1]['records'][0].date.year == date_group['records'][0].date.year
                        ):
                            final_batches[-1]['records'] += date_group['records']
                        else:
                            final_batches += [date_group]

                # Give the name based on previously computed values
                for batch in final_batches:
                    for move in batch['records']:
                        move.name = batch['format'].format(**batch['format_values'])
                        batch['format_values']['seq'] += 1
                    batch['records']._compute_split_sequence()

        self.filtered(lambda m: not m.name).name = '/'

    def _get_invoiced_lot_values(self):
        """ Get and prepare data to show a table of invoiced lot on the invoice's report. """
        self.ensure_one()

        if self.state == 'draft':
            return []

        sale_orders = self.mapped('invoice_line_ids.sale_line_ids.order_id')
        stock_move_lines = sale_orders.mapped('picking_ids.move_lines.move_line_ids')

        # Get the other customer invoices and refunds.
        ordered_invoice_ids = sale_orders.mapped('invoice_ids') \
            .filtered(lambda i: i.state not in ['draft', 'cancel']) \
            .sorted(lambda i: (i.invoice_date, i.id))

        # Get the position of self in other customer invoices and refunds.
        self_index = None
        i = 0
        for invoice in ordered_invoice_ids:
            if invoice.id == self.id:
                self_index = i
                break
            i += 1

        # Get the previous invoice if any.
        previous_invoices = ordered_invoice_ids[:self_index]
        last_invoice = previous_invoices[-1] if len(previous_invoices) else None

        # Get the incoming and outgoing sml between self.invoice_date and the previous invoice (if any).
        write_dates = [wd for wd in self.invoice_line_ids.mapped('write_date') if wd]
        self_datetime = max(write_dates) if write_dates else None
        last_write_dates = last_invoice and [wd for wd in last_invoice.invoice_line_ids.mapped('write_date') if wd]
        last_invoice_datetime = max(last_write_dates) if last_write_dates else None

        def _filter_incoming_sml(ml):
            if ml.state == 'done' and ml.location_id.usage == 'customer' and ml.lot_id:
                if last_invoice_datetime:
                    return last_invoice_datetime <= ml.date <= self_datetime
                else:
                    return ml.date <= self_datetime
            return False

        def _filter_outgoing_sml(ml):
            if ml.state == 'done' and ml.location_dest_id.usage == 'customer' and ml.lot_id:
                if last_invoice_datetime:
                    return last_invoice_datetime <= ml.date <= self_datetime
                else:
                    return ml.date <= self_datetime
            return False

        incoming_sml = stock_move_lines.filtered(_filter_incoming_sml)
        outgoing_sml = stock_move_lines.filtered(_filter_outgoing_sml)

        # Prepare and return lot_values
        qties_per_lot = defaultdict(lambda: 0)
        if self.move_type == 'out_refund':
            for ml in outgoing_sml:
                qties_per_lot[ml.lot_id] -= ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id)
            for ml in incoming_sml:
                qties_per_lot[ml.lot_id] += ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id)
        else:
            for ml in outgoing_sml:
                qties_per_lot[ml.lot_id] += ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id)
            for ml in incoming_sml:
                qties_per_lot[ml.lot_id] -= ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id)
        lot_values = []
        for lot_id, qty in qties_per_lot.items():
            if float_is_zero(qty, precision_rounding=lot_id.product_id.uom_id.rounding):
                continue
            lot_values.append({
                'product_name': lot_id.product_id.name,
                'quantity': qty,
                'uom_name': lot_id.product_uom_id.name,
                'lot_name': lot_id.name,
            })
        return lot_values

    x_with_signature = fields.Boolean("With Stamp & Signature", default=True)
    bill_attachment = fields.Binary('Attach Bill', attachment=True)
    x_studio_eway_bill_no = fields.Char('E-way Bill No.', default='')
    region_id = fields.Many2one('res.country.region', 'Region', related='partner_id.region_id', store=True)
    margin = fields.Monetary(compute='_product_margin',
                             currency_field='currency_id', store=True)
    margin_percentage = fields.Monetary(compute='_product_margin_per', string='Margin (%)',
                             currency_field='currency_id', store=True)
    total_purchase_price = fields.Monetary(compute='_get_total_cost', string='Total Cost',
                                           currency_field='currency_id', store=True)
    categ_id = fields.Many2many(related='partner_id.category_id',string="Tags")
    # name = fields.Char(string='Number', copy=False, compute='_compute_name',readonly=True, index=True, tracking=True)
    service_bill = fields.Boolean(compute='compute_is_a_service_bill')

    @api.depends('invoice_line_ids')
    def compute_is_a_service_bill(self):
        for rec in self:
            if rec.move_type == 'in_invoice':
                non_service_lines =[i if i.product_id and i.product_id.type =='service' else False for i in rec.invoice_line_ids]
                if non_service_lines and any(non_service_lines) != False:
                    rec.service_bill = False
                else:
                    rec.service_bill = True
            else:
                rec.service_bill = False

    @api.depends('invoice_line_ids.purchase_price_subtotal')
    def _get_total_cost(self):
        purchase_price_total = 0.0
        for move in self:
            if move.move_type == 'out_invoice':
                for line in move.invoice_line_ids:
                    purchase_price_total += line.purchase_price_subtotal
                move.total_purchase_price = purchase_price_total

    @api.depends('margin', 'amount_untaxed')
    def _product_margin_per(self):
        for move in self:
            if move.amount_untaxed != 0.0 and move.move_type == 'out_invoice':
                move.margin_percentage = (move.margin / move.amount_untaxed) * 100
            else:
                move.margin_percentage = 0.0

    @api.depends('invoice_line_ids.margin')
    def _product_margin(self):
        margin = 0.0
        for move in self:
            if move.amount_untaxed != 0.0 and move.move_type == 'out_invoice':
                for line in move.invoice_line_ids:
                    margin += line.margin
                move.margin = margin
            else:
                move.margin = 0.0


    def sales_person_due_followup(self):
        users = self.env['res.users'].sudo().search([])

        for user in users:
            body = """<p> Hello </p>"""+ user.name +""",
                    <br/><p> This is a reminder for due payments of your sales orders, below are the Invoices which are due for payment:</p><br/>
                    <table style="width:100%;border: 1px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Customer Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Invoice Number</th>
                                <th align="center" style="border: 1px solid black;color:white;">Invoice Date</th>
                                <th align="center" style="border: 1px solid black;color:white;">Credit Period</th>
                                <th align="center" style="border: 1px solid black;color:white;">Due Date</th>
                                <th align="center" style="border: 1px solid black;color:white;">Overdue Days</th>
                                <th align="center" style="border: 1px solid black;color:white;">Due Amount</th>
                            </tr>
                        </thead>
                        <tbody>"""
            invoices = self.sudo().search(
                [('invoice_user_id', '=', user.id), ('amount_residual', '>', 0), ('move_type', '=', 'out_invoice'),
                 ('state', '=', 'posted')])
            inv_list = []
            for inv in invoices:
                overdue_days = ((
                                            datetime.date.today() - inv.invoice_date_due).days) if datetime.date.today() > inv.invoice_date_due else 0
                inv_list.append({'overdue_days': overdue_days, 'inv': inv})
            if inv_list:
                inv_list.sort(key=operator.itemgetter('overdue_days'), reverse=True)

            for invoice in inv_list:
                inv = invoice.get('inv')
                amount_residual = inv.currency_id._convert(inv.amount_residual, inv.company_id.currency_id,
                                                           inv.company_id, inv.invoice_date, round=False)
                body += """
                        <tr style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{partner}</td>
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="left" style="border: 1px solid">{invoice_date}</td>
                            <td align="left" style="border: 1px solid">{credit_period}</td>
                            <td align="left" style="border: 1px solid">{due_date}</td>
                            <td align="left" style="border: 1px solid">{overdue_days}</td>
                            <td align="right" style="border: 1px solid">{due_amount}</td>
                        </tr>
                        """.format(partner=inv.partner_id.name or inv.partner_id.display_name, name=inv.name,
                                   invoice_date=datetime.date.strftime(inv.invoice_date, "%d/%m/%Y"),
                                   credit_period=inv.invoice_payment_term_id.name,
                                   due_date=datetime.date.strftime(inv.invoice_date_due, "%d/%m/%Y"),
                                   overdue_days=str(invoice.get('overdue_days')) + " Days",
                                   due_amount=format_currency(amount_residual, 'INR', locale='en_IN'), )
            body += """</tbody></table>"""
            if invoices:
                mail = self.env['mail.mail'].sudo().create({
                    'subject': """Reminder for Due Payments""",
                    'email_to': user.login,
                    'email_from': "odoo@eternitytechnologies.com",
                    'email_cc': "aman.chadha@eternitytechnologies.com,santosh.joshi@eternitytechnologies.com",
                    'reply_to': user.login,
                    'body_html': body
                })
                mail.send()


    # def _post(self, soft=True):
    #     """Use journal type to define document type because not miss state in any entry including POS entry"""
    #     posted = super()._post(soft)
    #     gst_treatment_name_mapping = {k: v for k, v in
    #                          self._fields['l10n_in_gst_treatment']._description_selection(self.env)}
    #     for move in posted.filtered(lambda m: m.l10n_in_company_country_code == 'IN'):
    #         """Check state is set in company/sub-unit"""
    #         company_unit_partner = move.journal_id.l10n_in_gstin_partner_id or move.journal_id.company_id
    #         if not company_unit_partner.state_id:
    #             raise ValidationError(_(
    #                 "State is missing from your company/unit %(company_name)s (%(company_id)s).\nFirst set state in your company/unit.",
    #                 company_name=company_unit_partner.name,
    #                 company_id=company_unit_partner.id
    #             ))
    #         elif self.journal_id.type == 'purchase':
    #             move.l10n_in_state_id = company_unit_partner.state_id
    #
    #         shipping_partner = move._l10n_in_get_shipping_partner()
    #         move.l10n_in_gstin = move._l10n_in_get_shipping_partner_gstin(shipping_partner)
    #         if not move.l10n_in_gstin and move.l10n_in_gst_treatment in ['regular', 'composition', 'special_economic_zone', 'deemed_export'] and move.partner_id == move.partner_shipping_id:
    #             raise ValidationError(_(
    #                 "Partner %(partner_name)s (%(partner_id)s) GSTIN is required under GST Treatment %(name)s",
    #                 partner_name=shipping_partner.name,
    #                 partner_id=shipping_partner.id,
    #                 name=gst_treatment_name_mapping.get(move.l10n_in_gst_treatment)
    #             ))
    #         if self.journal_id.type == 'sale':
    #             move.l10n_in_state_id = self._l10n_in_get_indian_state(shipping_partner)
    #             if not move.l10n_in_state_id:
    #                 move.l10n_in_state_id = self._l10n_in_get_indian_state(move.partner_id)
    #             #still state is not set then assumed that transaction is local like PoS so set state of company unit
    #             if not move.l10n_in_state_id:
    #                 move.l10n_in_state_id = company_unit_partner.state_id
    #     return posted


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # pan_num = fields.Char(string="Pancard", related="partner_id.pan")
    # untaxed_amount = fields.Monetary(string="Untaxed Amount", compute='_compute_untax_amt', store=True)
    #
    # def _compute_untax_amt(self):
    #     for rec in self:
    #         for move in rec.move_id.invoice_line_ids:
    #             if rec.product_id == move.product_id:
    #                 rec.untaxed_amount = move.price_subtotal

    @api.depends('product_id', 'purchase_price', 'quantity')
    def _get_cost_subtotal(self):
        for record in self:
            record.purchase_price_subtotal = record.purchase_price * record.quantity

    purchase_price_subtotal = fields.Float(
        string='Cost Subtotal', digits='Cost Subtotal',
        compute=_get_cost_subtotal, store=True
    )
    margin = fields.Float(compute='_product_margin', digits='Product Price', store=True, string='Margin')
    purchase_price = fields.Float(string='Cost', digits='Product Price')

    _sql_constraints = [(
            'check_non_accountable_fields_null',
             "CHECK(display_type NOT IN ('line_section', 'line_note') AND (amount_currency = 0 AND debit = 0 AND credit = 0 AND account_id IS NULL))",
             "Forbidden unit price, account and quantity on non-accountable invoice line"
        )]

    def get_tax_list(self):
        taxes = []
        for data in self:
            for tax_lines in data.tax_ids:
                taxes.append(tax_lines)
        return taxes

    def _get_computed_name(self):
        self.ensure_one()

        if not self.product_id:
            return ''

        if self.partner_id.lang:
            product = self.product_id.with_context(lang=self.partner_id.lang)
        else:
            product = self.product_id

        values = []
        # if product.partner_ref:
        #     values.append(product.name)
        if self.journal_id.type == 'sale':
            if product.description_sale:
                values.append(product.description_sale)
        elif self.journal_id.type == 'purchase':
            if product.description_purchase:
                values.append(product.description_purchase)
        if product.product_template_attribute_value_ids:
            for data in product.product_template_attribute_value_ids:
                if data.name == 'NA':
                    continue
                attributes = data.display_name
                values.append(attributes)
        return '\n'.join(values)

    def _compute_margin(self, move_id, product_id, product_uom_id):
        frm_cur = self.env.company.currency_id
        to_cur = move_id.currency_id
        purchase_price = product_id.standard_price
        if product_uom_id != product_id.uom_id:
            purchase_price = product_id.uom_id._compute_price(purchase_price, product_uom_id)
        price = frm_cur._convert(
            purchase_price, to_cur, move_id.company_id or self.env.company,
            move_id.date or fields.Date.today(), round=False)
        return price

    @api.onchange('product_id', 'product_uom_id')
    def product_id_change_margin(self):
        if self.move_id.move_type == 'out_invoice':
            if not self.product_id or not self.product_uom_id:
                return
            self.purchase_price = self._compute_margin(self.move_id, self.product_id, self.product_uom_id)



    @api.depends('product_id', 'purchase_price', 'quantity', 'price_unit', 'price_subtotal')
    def _product_margin(self):
        for line in self:
            if line.move_id.move_type == 'out_invoice':
                currency = line.move_id.currency_id
                price = line.purchase_price
                margin = line.price_subtotal - (price * line.quantity)
                line.margin = currency.round(margin) if currency else margin
            else:
                line.margin = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'purchase_price' not in vals:
                move_id = self.env['account.move'].browse(vals.get('move_id'))
                product_id = self.env['product.product'].browse(vals.get('product_id'))
                product_uom_id = self.env['uom.uom'].browse(vals.get('product_uom_id'))
                if move_id.move_type == 'out_invoice':
                    vals['purchase_price'] = self._compute_margin(move_id, product_id, product_uom_id)
        return super(AccountMoveLine, self).create(vals_list)
