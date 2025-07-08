from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.addons.stock.models.stock_rule import ProcurementException
from collections import defaultdict
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.tools import OrderedSet
from dateutil.relativedelta import relativedelta
from collections import defaultdict, namedtuple


class StockMove(models.Model):
    _inherit = 'stock.move'

    finished_lot_ids = fields.Many2one('stock.lot', string="Lots")
    custom_product_uom_qty = fields.Float("Partial qty to consume")
    price_unit = fields.Float(
        'Unit Price',
        help="Technical field used to record the product cost set by the user during a picking confirmation (when costing "
             "method used is 'average price' or 'real'). Value given in company currency and in product uom.",store=True)

    @api.onchange('lot_ids', 'custom_product_uom_qty')
    def verify_lot_and_qty_to_consume(self):
        if self.picking_type_id.code == 'incoming' or self.custom_product_uom_qty == 0:
            return {}
        if self.custom_product_uom_qty < 0:
            raise ValidationError('You are not allowed to enter quantity in negative')
        domain = [('product_id', '=', self.product_id.id), ('location_id', '=', self.location_id.id)]
        if self.product_id.tracking in ['lot', 'serial']:
            domain.append(('lot_id', '=', self.lot_ids and self.lot_ids.id or False))
        location_id = self.env['stock.quant'].search(domain)
        qty = sum(location_id.mapped('quantity'))
        prd_name = self.product_id.name
        default_code = self.product_id.default_code
        if self.product_id.tracking in ['lot', 'serial'] and not self.lot_ids:
            raise ValidationError(f" Enter the lot/serial number for {prd_name}[{default_code}]")
        elif self.lot_ids and self.custom_product_uom_qty > qty:
            raise ValidationError(
                f" Done quantity is greater than lot/serial quantity {qty} for {prd_name}[{default_code}] at location {self.location_id.name}")
        elif self.product_id.tracking == 'none' and self.custom_product_uom_qty > qty:
            raise ValidationError(
                f" Done quantity is greater than On Hand Qty({qty}) for {prd_name}[{default_code}] at location {self.location_id.name}")

    def _create_account_move_line(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost):
        self.ensure_one()
        AccountMove = self.env['account.move'].with_context(default_journal_id=journal_id)

        move_lines = self._prepare_account_move_line(qty, cost, credit_account_id, debit_account_id, description)
        if move_lines:
            date = self._context.get('force_period_date', fields.Date.context_today(self))
            new_account_move = AccountMove.sudo().create({
                'journal_id': journal_id,
                'line_ids': move_lines,
                'date': date,
                'ref': description,
                'stock_move_id': self.id,
                'stock_valuation_layer_ids': [(6, None, [svl_id])],
                'move_type': 'entry',
            })
            new_account_move._post()
        # angalo_saxon_enabled = self.env.company.use_anglo_saxon or self.env['ir.config_parameter'].sudo().get_param('account_accountant.use_anglo_saxon')
        # if self.created_production_id.__class__.__name__=='mrp.production':
        if self.production_id:
            valuation = self.env['stock.valuation.layer'].search([('id','=',svl_id)])
            accs = valuation.product_id.product_tmpl_id.get_product_accounts()
            mo_move_lines = self._prepare_account_move_line(qty, cost,accs['stock_output'].id,credit_account_id,description)
            if mo_move_lines:
                date = self._context.get('force_period_date', fields.Date.context_today(self))
                mo_account_move = AccountMove.sudo().create({
                    'journal_id': journal_id,
                    'line_ids': mo_move_lines,
                    'date': date,
                    'ref': description,
                    'stock_move_id': self.id,
                    'move_type': 'entry',
                })
                mo_account_move._post()


class MoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.depends('reference', 'origin')
    def fetch_partner(self):
        for rec in self:
            if rec.reference:
                mrp = self.env['mrp.production'].search([('name','=',rec.reference)])
                if mrp and mrp.untaxed_amount_updated:
                    rec.partner_id = mrp.partner_id.id
                else:
                    sale = self.env['sale.order'].search([('name', '=', rec.reference)])
                    rec.partner_id = sale.partner_id.id

                # return partner.id
            elif not rec.reference and rec.origin:
                mrp = self.env['mrp.production'].search([('name', '=', rec.origin)])
                if mrp and mrp.untaxed_amount_updated:
                    rec.partner_id = mrp.partner_id.id
                else:
                    sale = self.env['sale.order'].search([('name', '=', rec.origin)])
                    rec.partner_id = sale.partner_id.id
                # return partner.id
            else:
                rec.partner_id = False
                # return False

    partner_id = fields.Many2one('res.partner', compute='fetch_partner', string="Customer")

    # def _action_done(self):
    #     """ This method is called during a move's `action_done`. It'll actually move a quant from
    #     the source location to the destination location, and unreserve if needed in the source
    #     location.
    #
    #     This method is intended to be called on all the move lines of a move. This method is not
    #     intended to be called when editing a `done` move (that's what the override of `write` here
    #     is done.
    #     """
    #     Quant = self.env['stock.quant']
    #
    #     # First, we loop over all the move lines to do a preliminary check: `qty_done` should not
    #     # be negative and, according to the presence of a picking type or a linked inventory
    #     # adjustment, enforce some rules on the `lot_id` field. If `qty_done` is null, we unlink
    #     # the line. It is mandatory in order to free the reservation and correctly apply
    #     # `action_done` on the next move lines.
    #     ml_ids_tracked_without_lot = OrderedSet()
    #     ml_ids_to_delete = OrderedSet()
    #     ml_ids_to_create_lot = OrderedSet()
    #     for ml in self:
    #         # Check here if `ml.qty_done` respects the rounding of `ml.product_uom_id`.
    #         uom_qty = float_round(ml.quantity, precision_rounding=ml.product_uom_id.rounding, rounding_method='HALF-UP')
    #         precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
    #         quantity = float_round(ml.quantity, precision_digits=precision_digits, rounding_method='HALF-UP')
    #         if float_compare(uom_qty, quantity, precision_digits=precision_digits) != 0:
    #             raise UserError(_('The quantity done for the product "%s" doesn\'t respect the rounding precision \
    #                               defined on the unit of measure "%s". Please change the quantity done or the \
    #                               rounding precision of your unit of measure.') % (ml.product_id.display_name, ml.product_uom_id.name))
    #
    #         qty_done_float_compared = float_compare(ml.quantity, 0, precision_rounding=ml.product_uom_id.rounding)
    #         if qty_done_float_compared > 0:
    #             if ml.product_id.tracking != 'none':
    #                 picking_type_id = ml.move_id.picking_type_id
    #                 if picking_type_id:
    #                     if picking_type_id.use_create_lots:
    #                         # If a picking type is linked, we may have to create a production lot on
    #                         # the fly before assigning it to the move line if the user checked both
    #                         # `use_create_lots` and `use_existing_lots`.
    #                         if ml.lot_name and not ml.lot_id:
    #                             lot = self.env['stock.lot'].search([
    #                                 ('company_id', '=', ml.company_id.id),
    #                                 ('product_id', '=', ml.product_id.id),
    #                                 ('name', '=', ml.lot_name),
    #                             ], limit=1)
    #                             if lot:
    #                                 ml.lot_id = lot.id
    #                             else:
    #                                 ml_ids_to_create_lot.add(ml.id)
    #                     elif not picking_type_id.use_create_lots and not picking_type_id.use_existing_lots:
    #                         # If the user disabled both `use_create_lots` and `use_existing_lots`
    #                         # checkboxes on the picking type, he's allowed to enter tracked
    #                         # products without a `lot_id`.
    #                         continue
    #                 # elif ml.move_id.inventory_id:
    #                 #     # If an inventory adjustment is linked, the user is allowed to enter
    #                 #     # tracked products without a `lot_id`.
    #                 #     continue
    #
    #                 if (not ml.lot_id and ml.id not in ml_ids_to_create_lot) and not ml.move_id.lot_ids:
    #                     ml_ids_tracked_without_lot.add(ml.id)
    #         elif qty_done_float_compared < 0:
    #             raise UserError(_('No negative quantities allowed'))
    #         else:
    #             ml_ids_to_delete.add(ml.id)
    #
    #     if ml_ids_tracked_without_lot:
    #         mls_tracked_without_lot = self.env['stock.move.line'].browse(ml_ids_tracked_without_lot)
    #         raise UserError(_('You need to supply a Lot/Serial Number for product: \n - ') +
    #                           '\n - '.join(mls_tracked_without_lot.mapped('product_id.display_name')))
    #     ml_to_create_lot = self.env['stock.move.line'].browse(ml_ids_to_create_lot)
    #     ml_to_create_lot._create_and_assign_production_lot()
    #
    #     mls_to_delete = self.env['stock.move.line'].browse(ml_ids_to_delete)
    #     mls_to_delete.unlink()
    #
    #     mls_todo = (self - mls_to_delete)
    #     mls_todo._check_company()
    #
    #     # Now, we can actually move the quant.
    #     ml_ids_to_ignore = OrderedSet()
    #     for ml in mls_todo:
    #         if ml.product_id.type == 'product':
    #             rounding = ml.product_uom_id.rounding
    #
    #             # if this move line is force assigned, unreserve elsewhere if needed
    #             if not ml.move_id._should_bypass_reservation(ml.location_id) and float_compare(ml.quantity, ml.quantity_product_uom, precision_rounding=rounding) > 0:
    #                 qty_done_product_uom = ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id, rounding_method='HALF-UP')
    #                 extra_qty = qty_done_product_uom - ml.quantity
    #                 ml_to_ignore = self.env['stock.move.line'].browse(ml_ids_to_ignore)
    #                 ml._free_reservation(ml.product_id, ml.location_id, extra_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, ml_to_ignore=ml_to_ignore)
    #             # unreserve what's been reserved
    #             if not ml.move_id._should_bypass_reservation(ml.location_id) and ml.product_id.type == 'product' and ml.quantity:
    #                 try:
    #                     Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.quantity, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
    #                 except UserError:
    #                     Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.quantity, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
    #
    #             # move what's been actually done
    #             quantity = ml.product_uom_id._compute_quantity(ml.quantity, ml.move_id.product_id.uom_id, rounding_method='HALF-UP')
    #             available_qty, in_date = Quant._update_available_quantity(ml.product_id, ml.location_id, -quantity, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
    #             if available_qty < 0 and ml.lot_id:
    #                 # see if we can compensate the negative quants with some untracked quants
    #                 untracked_qty = Quant._get_available_quantity(ml.product_id, ml.location_id, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
    #                 if untracked_qty:
    #                     taken_from_untracked_qty = min(untracked_qty, abs(quantity))
    #                     Quant._update_available_quantity(ml.product_id, ml.location_id, -taken_from_untracked_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id)
    #                     Quant._update_available_quantity(ml.product_id, ml.location_id, taken_from_untracked_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
    #             Quant._update_available_quantity(ml.product_id, ml.location_dest_id, quantity, lot_id=ml.lot_id, package_id=ml.result_package_id, owner_id=ml.owner_id, in_date=in_date)
    #         ml_ids_to_ignore.add(ml.id)
    #     # Reset the reserved quantity as we just moved it to the destination location.
    #     mls_todo.with_context(bypass_reservation_update=True).write({
    #         'quantity_product_uom': 0.00,
    #         'date': fields.Datetime.now(),
    #     })


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # added below fields for migration
    ewaybill_no = fields.Char("E-way Bill No", copy=False, tracking=2)
    generate_ewaybill = fields.Boolean("E-Way Bill?", help='Generate E-way Bill?')


    def action_done(self):
        rec = super(StockPicking, self).action_done()
        if self.move_line_ids_without_package:
            for lines in self.move_line_ids_without_package:
                if lines.lot_id and self.date_done:
                    lines.lot_id.delivery_date = self.date_done.strftime('%Y-%m-%d')
        return rec


class StockLocation(models.Model):
    _inherit = 'stock.location'

    def _should_be_valued(self):
        """ This method returns a boolean reflecting whether the products stored in `self` should
        be considered when valuating the stock of a company.
        """
        # self.ensure_one()
        if self.usage == 'internal' or (self.usage == 'transit' and self.company_id):
            return True
        return False

    def should_bypass_reservation(self):
        # self.ensure_one()
        return self.usage in ('supplier', 'customer', 'inventory', 'production') or self.scrap_location or (self.usage == 'transit' and not self.company_id)


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_id, name, origin, company_id,values, bom):
        date_planned = self._get_date_planned(bom, values)
        date_deadline = values.get('date_deadline') or date_planned + relativedelta(days=company_id.manufacturing_lead) + relativedelta(days=product_id.produce_delay)
        order = self.env['sale.order'].search([('name','=',origin)],limit=1)


        return {
            'origin': origin,
            'product_id': product_id.id,
            'product_description_variants': values.get('product_description_variants'),
            'product_qty': product_qty,
            'product_uom_id': product_uom.id,
            'location_src_id': self.location_src_id.id or self.picking_type_id.default_location_src_id.id or location_id.id,
            'location_dest_id': location_id.id,
            'bom_id': bom.id,
            'date_deadline': date_deadline,
            'date_start': date_planned,
            'procurement_group_id': False,
            'propagate_cancel': self.propagate_cancel,
            'orderpoint_id': values.get('orderpoint_id', False) and values.get('orderpoint_id').id,
            'picking_type_id': self.picking_type_id.id or values['warehouse_id'].manu_type_id.id,
            'company_id': company_id.id,
            'move_dest_ids': values.get('move_dest_ids') and [(4, x.id) for x in values['move_dest_ids']] or False,
            'user_id': False,
            'client_order_ref': order.po_number if order else "",
            # 'delivery_date': order.commitment_date if order else False,
            'partner_id': order.partner_id.id if order else False,
        }

    @api.model
    def _run_manufacture(self, procurements):
        productions_values_by_company = defaultdict(list)
        errors = []
        for procurement, rule in procurements:
            bom = self._get_matching_bom(procurement.product_id, procurement.company_id, procurement.values)
            if not bom:
                msg = _(
                    'There is no Bill of Material of type manufacture or kit found for the product %s. Please define a Bill of Material for this product.') % (
                      procurement.product_id.display_name,)
                errors.append((procurement, msg))

            productions_values_by_company[procurement.company_id.id].append(rule._prepare_mo_vals(*procurement, bom))

        if errors:
            raise ProcurementException(errors)

        for company_id, productions_values in productions_values_by_company.items():
            # create the MO as SUPERUSER because the current user may not have the rights to do it (mto product launched by a sale for example)
            productions = self.env['mrp.production'].with_user(SUPERUSER_ID).sudo().with_company(company_id).create(
                productions_values)
            self.env['stock.move'].sudo().create(productions._get_moves_raw_values())
            self.env['stock.move'].sudo().create(productions._get_moves_finished_values())
            productions._compute_workorder_ids()
            # productions.filtered(lambda p: p.move_raw_ids).action_confirm()

            for production in productions:
                origin_production = production.move_dest_ids and production.move_dest_ids[
                    0].raw_material_production_id or False
                orderpoint = production.orderpoint_id
                if orderpoint:
                    production.message_post_with_view('mail.message_origin_link',
                                                      values={'self': production, 'origin': orderpoint},
                                                      subtype_id=self.env.ref('mail.mt_note').id)
                if origin_production:
                    production.message_post_with_view('mail.message_origin_link',
                                                      values={'self': production, 'origin': origin_production},
                                                      subtype_id=self.env.ref('mail.mt_note').id)
        return True

