from odoo import api, fields, models, exceptions, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare, float_round


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def get_overdue_invoices(self):
        for rec in self:
            invoice_obj = self.env['account.move']
            move_ids = invoice_obj.search([
                ('partner_id', '=', rec.partner_id.id),
                ('payment_state', '=', 'not_paid'),
                ('invoice_date_due', '<', datetime.today()),
                ('state', '=', 'posted'),
            ])
            return move_ids

    def find_for_invoice_approval(self):
        for rec in self:
            invoice_obj = self.env['account.move']
            move_ids = invoice_obj.search([
                ('partner_id', '=', rec.partner_id.id),
                ('payment_state', '=', 'not_paid'),
                ('invoice_date_due', '<', datetime.today()),
                ('state', '=', 'posted'),
            ])
            total_residual = 0.0
            for data in move_ids:
                total_residual += data.amount_residual_signed
            rec.residual_amount = total_residual
            if rec.residual_amount > 0.0 and rec.invoice_creation_approved is True and rec.invoice_created is True:
                rec.apply_invoice_approval = False
            if rec.residual_amount > 0.0 and rec.invoice_creation_approved is False and rec.invoice_created is False:
                rec.apply_invoice_approval = True
            if rec.residual_amount == 0.0:
                rec.apply_invoice_approval = False
                rec.invoice_creation_approved = True
                rec.sent_for_invoice_approval = False
                rec.invoice_created = True

    production_ids = fields.One2many('mrp.production', compute="_compute_production_ids",
                                     string='Related MO Orders')
    production_count = fields.Integer(compute="_compute_production_count",
                                      string='MO Count')
    invoice_approval = fields.Boolean("Invoice approval", copy=False, default=False)
    create_invoice = fields.Boolean("Can Create Invoice", copy=False, default=False)
    create_invoice_invisible = fields.Boolean("Create Invisible", copy=False, default=False)
    approval_invoice_invisible = fields.Boolean("Approval Invisible", copy=False, default=False)
    default_invoice_invisible = fields.Boolean("Default Invoice Button Invisible", copy=False, default=False)

    apply_invoice_approval = fields.Boolean("Apply Invoice Approval", copy=False)
    sent_for_invoice_approval = fields.Boolean("Sent for Invoice Approval", copy=False)
    invoice_creation_approved = fields.Boolean("Invoice Creation Approved", copy=False, default=False)
    invoice_created = fields.Boolean("Invoice Created", copy=False, default=False)
    residual_amount = fields.Monetary(string='Amount Overdue', copy=False,
                                      compute='find_for_invoice_approval', )
    categ_id = fields.Many2many(related='partner_id.category_id', string="Tags")
    gst_treat = fields.Boolean()
    my_activity_date_deadline = fields.Char(string="My activity")

    def action_cancel(self):
        for mo in self.production_ids:
            if mo.state not in ('done','cancel'):
                raise UserError(_('Please cancel the corresponding manufacturing orders first!'))
        res = super(SaleOrder, self).action_cancel()
        return res

    @api.depends('name')
    def _compute_production_count(self):
        production_obj = self.env['mrp.production']
        for order in self:
            production_recs = production_obj.search([('origin', '=', order.name)])
            order.production_count = len(production_recs.ids)

    @api.depends('name')
    def _compute_production_ids(self):
        production_obj = self.env['mrp.production']
        for order in self:
            order.production_ids = production_obj.search([('origin', '=', order.name)])

    def view_production_orders(self):
        '''
        This function returns an action that display related production orders
        of current sales order.'''
        action = self.env.ref('mrp.mrp_production_action').read()[0]
        production_recs = self.mapped('production_ids')
        if len(production_recs) > 1:
            action['domain'] = [('id', 'in', production_recs.ids)]
        elif production_recs:
            action['views'] = [(self.env.ref('mrp.mrp_production_form_view').id, 'form')]
            action['res_id'] = production_recs.id
        return action

    def create_mo_script(self):
        order_ids = self.search([('confirmation_date', '>=', '2020-04-01'), ('state', '=', 'sale')])
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'mrp_operation'),
            (
                'warehouse_id.company_id', 'in',
                [self.env.context.get('company_id', self.env.user.company_id.id), False])],
            limit=1)
        mrp = self.env['mrp.production']
        counter = 0
        for order in order_ids:
            if not order.production_ids:
                for line in order.order_line:
                    mrp_vals = {}
                    if 1 in line.product_id.route_ids.ids and line.product_id.bom_count:
                        bom = self.env['mrp.bom']._bom_find(product=line.product_id, picking_type=picking_type,
                                                            company_id=order.company_id.id, bom_type='normal')
                        mrp_vals = {
                            'product_qty': line.product_uom_qty,
                            'origin': order.name,
                            'date_planned_start': order.confirmation_date,
                            'create_date': order.confirmation_date,
                            'company_id': order.company_id.id,
                            'product_id': line.product_id.id,
                            'product_uom_id': line.product_uom.id,
                            'picking_type_id': 8,
                            'bom_id': bom.id,
                        }
                        counter += 1
                        mrp_data = mrp.new(mrp_vals)
                        mrp_data._onchange_bom_id()
                        new_vals = mrp_data._convert_to_write(mrp_data._cache)
                        production = mrp.create(new_vals)
                        production._onchange_move_raw()
                        production.action_confirm()

    @api.onchange('commitment_date')
    def onchange_commitment_date(self):
        mrp = self.env['mrp.production'].search([('origin', '=', self.name)])
        if mrp:
            for data in mrp:
                data.update({'delivery_date': self.commitment_date})


    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        self.ensure_one()
        # journal = self.env['account.move'].with_context(default_move_type='out_invoice')._search_default_journal()
        # if not journal:
        #     raise UserError(_('Please define an accounting sales journal for the company %s (%s).') % (self.company_id.name, self.company_id.id))

        invoice_vals = {
            'ref': self.client_order_ref or '',
            'po_number': self.po_number or '',
            'move_type': 'out_invoice',
            'narration': self.note,
            'currency_id': self.pricelist_id.currency_id.id,
            'campaign_id': self.campaign_id.id,
            'medium_id': self.medium_id.id,
            'source_id': self.source_id.id,
            'invoice_user_id': self.user_id and self.user_id.id,
            'team_id': self.team_id.id,
            'partner_billing_id': self.partner_invoice_id.id,
            'partner_id': self.partner_id.id,
            'partner_shipping_id': self.partner_shipping_id.id,
            'fiscal_position_id': self.fiscal_position_id.id or self.partner_invoice_id.property_account_position_id.id,
            'invoice_origin': self.name,
            # 'journal_id': journal.id,  # company comes from the journal
            'invoice_payment_term_id': self.payment_term_id.id,
            'payment_reference': self.reference,
            'transaction_ids': [(6, 0, self.transaction_ids.ids)],
            'invoice_line_ids': [],
            'company_id': self.company_id.id,
        }
        return invoice_vals

    @api.depends('procurement_group_id.stock_move_ids.created_production_id.procurement_group_id.mrp_production_ids')
    def _compute_mrp_production_count(self):
        # data = self.env['procurement.group'].read_group([('sale_id', 'in', self.ids)], ['ids:array_agg(id)'],
        #                                                 ['sale_id'])

        # mrp_count = dict()
        # for item in data:
        #     procurement_groups = self.env['procurement.group'].browse(item['ids'])
        #     mrp_count[item['sale_id'][0]] = len(
        #         set(procurement_groups.stock_move_ids.created_production_id.procurement_group_id.mrp_production_ids.ids) |
        #         set(procurement_groups.mrp_production_ids.ids))
        for sale in self:
            mos = self.env['mrp.production'].sudo().search([('origin', '=', sale.name)])
            sale.mrp_production_count = len(mos)

    def action_view_mrp_production(self):
        self.ensure_one()
        # procurement_groups = self.env['procurement.group'].search([('sale_id', 'in', self.ids)])
        # mrp_production_ids = set(
        #     procurement_groups.stock_move_ids.created_production_id.procurement_group_id.mrp_production_ids.ids) | \
        #                      set(procurement_groups.mrp_production_ids.ids)
        mos = self.env['mrp.production'].sudo().search([('origin', '=', self.name)])

        action = {
            'res_model': 'mrp.production',
            'type': 'ir.actions.act_window',
        }
        if len(mos) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': mos.id,
            })
        else:
            action.update({
                'name': _("Manufacturing Orders Generated by %s", self.name),
                'domain': [('id', 'in', mos.ids)],
                'view_mode': 'list,form',
            })
        return action
# class SaleOrderLine(models.Model):
#     _inherit = 'sale.order.line'
#
#     del_date = fields.Date("Delivery Date")


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    @api.model
    def default_get(self, fields):
        res = super(SaleAdvancePaymentInv, self).default_get(fields)
        context = self._context
        sale_obj = self.env['sale.order']
        active_id = context.get('active_id')
        if active_id:
            search_id = sale_obj.browse(active_id)
            if search_id.invoice_count >=1:
                search_id.invoice_created = True
                search_id.invoice_creation_approved = False
        return res

    def create_invoices(self):
        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
        customers_invoices = self.env['account.move'].search([('partner_id', '=', sale_orders.partner_id.id)])
        print(customers_invoices)
        collect_total = 0.0
        for amt in customers_invoices:
            collect_total += amt.amount_total
            print(amt)
        print(collect_total)
        if collect_total > 5000000.0:
            print("cost is greater 5000000")
        for sale in sale_orders:
            mrps = self.env['mrp.production'].search([('origin', '=', sale.name)])
            if mrps:
                allow = False
                for mrp in mrps:
                    if mrp.state == 'done':
                        allow = True
                # Commented temporary
                if allow == False:
                    raise UserError(_('Any of the manufacturing order for this sale order is not done yet !!'))
        if self.advance_payment_method == 'delivered':
            sale_orders._create_invoices(final=self.deduct_down_payments)
        else:
            # Create deposit product if necessary
            if not self.product_id:
                vals = self._prepare_down_payment_product_values()
                self.product_id = self.env['product.product'].create(vals)
                self.env['ir.config_parameter'].sudo().set_param('sale.default_deposit_product_id', self.product_id.id)

            sale_line_obj = self.env['sale.order.line']
            for order in sale_orders:
                amount, name = self._get_advance_details(order)

                if self.product_id.invoice_policy != 'order':
                    raise UserError(_('The product used to invoice a down payment should have an invoice policy set to "Ordered quantities". Please update your deposit product to be able to create a deposit invoice.'))
                if self.product_id.type != 'service':
                    raise UserError(_("The product used to invoice a down payment should be of type 'Service'. Please use another product or update this product."))
                taxes = self.product_id.taxes_id.filtered(lambda r: not order.company_id or r.company_id == order.company_id)
                tax_ids = order.fiscal_position_id.map_tax(taxes, self.product_id, order.partner_shipping_id).ids
                analytic_tag_ids = []
                for line in order.order_line:
                    analytic_tag_ids = [(4, analytic_tag.id, None) for analytic_tag in line.analytic_tag_ids]

                so_line_values = self._prepare_so_line(order, analytic_tag_ids, tax_ids, amount)
                so_line = sale_line_obj.create(so_line_values)
                self._create_invoice(order, so_line, amount)
        if self._context.get('open_invoices', False):
            return sale_orders.action_view_invoice()
        return {'type': 'ir.actions.act_window_close'}

    def _prepare_invoice_values(self, order, name, amount, so_line):
        invoice_vals = {
            'ref': order.client_order_ref,
            'move_type': 'out_invoice',
            'invoice_origin': order.name,
            'invoice_user_id': order.user_id.id,
            'narration': order.note,
            'partner_id': order.partner_id.id,
            'partner_billing_id': order.partner_invoice_id.id,
            'fiscal_position_id': (order.fiscal_position_id or order.fiscal_position_id.get_fiscal_position(order.partner_id.id)).id,
            'partner_shipping_id': order.partner_shipping_id.id,
            'currency_id': order.pricelist_id.currency_id.id,
            'payment_reference': order.reference,
            'invoice_payment_term_id': order.payment_term_id.id,
            'partner_bank_id': order.company_id.partner_id.bank_ids[:1].id,
            'team_id': order.team_id.id,
            'invoice_incoterm_id': order.incoterm.id,
            'campaign_id': order.campaign_id.id,
            'medium_id': order.medium_id.id,
            'source_id': order.source_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': name,
                'price_unit': amount,
                'quantity': 1.0,
                'product_id': self.product_id.id,
                'product_uom_id': so_line.product_uom.id,
                'tax_ids': [(6, 0, so_line.tax_id.ids)],
                'sale_line_ids': [(6, 0, [so_line.id])],
                'analytic_tag_ids': [(6, 0, so_line.analytic_tag_ids.ids)],
                'analytic_account_id': order.analytic_account_id.id or False,
            })],
        }

        return invoice_vals



