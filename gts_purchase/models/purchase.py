from odoo import api, fields, models, _
from odoo import exceptions
from odoo.exceptions import UserError, ValidationError
from datetime import datetime


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    gst_treat = fields.Boolean(compute='compute_gst_treatment')
    stock_status = fields.Selection(selection=[('pending', 'Pending'), ('received','Received')], string="Stock Status",
                                    compute='update_stock_status')
    special_po = fields.Boolean("Special PO ?")

    @api.depends('order_line', 'order_line.product_id', 'order_line.qty_received', 'order_line.product_qty')
    def update_stock_status(self):
        for rec in self:
            stock_status = 'received'
            if rec.order_line:
                for line in rec.order_line:
                    if line.qty_received < line.product_qty:
                        stock_status = 'pending'
            else:
                stock_status = 'pending'
            rec.stock_status = stock_status

    # @api.onchange('partner_id')
    # def update_fiscal_position(self):
    #     company = self.env.company
    #     if self.partner_id:
    #         if self.partner_id.state_id == company.state_id:
    #             self.fiscal_position_id = False
    #         else:
    #             interstate = self.env['account.fiscal.position'].search([('name', '=', 'Inter State')])
    #             self.fiscal_position_id = interstate.id

    @api.depends('partner_id')
    def compute_gst_treatment(self):
        if self.partner_id:
            self.gst_treat = True
            self.l10n_in_gst_treatment = self.partner_id.l10n_in_gst_treatment
        else:
            self.gst_treat = False

    def button_confirm(self):
        rec = super(PurchaseOrder, self).button_confirm()
        if self.partner_id.l10n_in_gst_treatment not in ['unregistered', 'consumer', 'overseas'] and not \
                self.partner_id.vat and self.partner_id.company_type == 'company':
            raise UserError(_('Please enter GSTIN Number for the Vendor.'))
        elif self.partner_id.company_type == 'person' and self.partner_id.parent_id and not \
                self.partner_id.parent_id.l10n_in_gst_treatment not in ['unregistered', 'consumer', 'overseas']\
                and not self.partner_id.parent_id.vat:
            raise UserError(_('Please enter GSTIN Number for the Vendor.'))
        return rec

    x_dead_date = fields.Date('RFQ Dead Line')
    x_with_signature = fields.Boolean('With Signature & Stamp', default=True)


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    unit_pallet_qty = fields.Float("Unit Pallet Qty")
    pallets = fields.Float("Pallets", compute='compute_pallet_qty')
    balance_qty = fields.Float("Excess/Reqd. Pallet Qty", compute='compute_pallet_qty')
    excess_qty = fields.Boolean(compute='compute_pallet_qty')
    lst_pur_price = fields.Float(string="Last Purchase Price", compute='_get_lst_pur_price')
    qty_to_rcv = fields.Integer(string="Qty To Receive", compute='_compute_qty_to_rcv')

    # By Cj
    @api.onchange('product_qty', 'qty_received')
    def _compute_qty_to_rcv(self):
        for rec in self:
            rec.qty_to_rcv = rec.product_qty - rec.qty_received

    @api.onchange('product_id')
    def _get_lst_pur_price(self):
        for rec in self:
            rec.lst_pur_price = 0
            if rec.product_id:
                domain = [('order_line.id', '!=', rec.id or None), ('order_line.product_id', '=', rec.product_id.id),
                          ('state', '=', 'purchase'), ('date_approve', '<', rec.order_id.date_approve or datetime.now())]
                lst_pur_ord = self.env['purchase.order'].search(domain, order='date_approve desc', limit=1)
                for prd in lst_pur_ord:
                    for line in prd.order_line:
                        if line.product_id == rec.product_id:
                            rec.lst_pur_price = line.price_unit or 0
    # END CJ

    @api.onchange('product_id')
    def set_product_pallet_qty(self):
        if self.product_id:
           self.unit_pallet_qty = self.product_id.pallet_qty

    # By Nitin
    # @api.depends('product_id', 'product_qty', 'unit_pallet_qty')
    # def compute_pallet_qty(self):
    #     for rec in self:
    #         if rec.order_id.special_po and rec.product_id:
    #             if rec.unit_pallet_qty > rec.product_qty:
    #                 rem = round(rec.unit_pallet_qty - rec.product_qty)
    #                 rec.excess_qty = False
    #                 rec.balance_qty = rem
    #                 rec.pallets = 0
    #             if rec.unit_pallet_qty < rec.product_qty:
    #                 quot = int(rec.product_qty / rec.unit_pallet_qty)
    #                 rem = round(rec.product_qty % rec.unit_pallet_qty)
    #                 rec.excess_qty = True
    #                 rec.balance_qty = rem
    #                 rec.pallets = float(quot)
    #             if rec.unit_pallet_qty == rec.product_qty:
    #                 rec.excess_qty = False
    #                 rec.pallets = 1
    #                 rec.balance_qty = 0
    #         else:
    #             rec.excess_qty = False
    #             rec.pallets = 0
    #             rec.balance_qty = 0

    # By CJ
    @api.depends('product_id', 'product_qty', 'unit_pallet_qty')
    def compute_pallet_qty(self):
        for rec in self:
            rec.excess_qty, rec.pallets, rec.balance_qty = False, 0, 0
            if rec.order_id.special_po and rec.product_id:
                if rec.unit_pallet_qty == 0:
                    raise ValidationError("Please set Unit Pallet Quantity For Product")
                quot = rec.product_qty / rec.unit_pallet_qty
                rec.pallets, rec.excess_qty = quot, False
                if quot > 1 and (quot % 1 != 0):
                    rec.excess_qty = True
                    rec.balance_qty = rec.product_qty - (rec.unit_pallet_qty * int(quot))
                elif quot > 1 and (quot % 1 == 0):
                    rec.balance_qty = 0
                else:
                    rec.balance_qty = (rec.unit_pallet_qty - rec.product_qty)
    # End CJ

    def get_tax_list(self):
        taxes = []
        for data in self:
            for tax_lines in data.taxes_id:
                taxes.append(tax_lines)
        return taxes

    @api.onchange('product_id')
    def onchange_product_id(self):
        rec = super(PurchaseOrderLine, self).onchange_product_id()
        if self.product_id:
            attributes, description = '', ''
            if self.product_id.product_template_attribute_value_ids:
                for data in self.product_id.product_template_attribute_value_ids:
                    if data.name == 'NA':
                        continue
                    attributes += "\n" + data.display_name
            if self.product_id.description_purchase:
                description = self.product_id.description_purchase
            self.name = description + attributes
        return rec
