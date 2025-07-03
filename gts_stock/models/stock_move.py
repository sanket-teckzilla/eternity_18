from odoo import api, fields, tools, models, _


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def button_unreserve(self):
        res = super(MrpProduction, self).button_unreserve()
        list = []
        for line in self.move_raw_ids:
            line.lot_ids_reserved = [(6, 0, list)]
            line.stock_lot_ids = [(6, 0, list)]
            line.lot_with_qty = ''
            line.lot_with_qty_reserved = ''
        return res


# class MrpProductProduce(models.TransientModel):
#     _inherit = "mrp.product.produce"
#
#     def continue_production(self):
#         res = super(MrpProductProduce, self).continue_production()
#         mo_id = self.env['mrp.production'].search([('id', '=', self.production_id.id)])
#         if mo_id:
#             for line in mo_id.move_raw_ids:
#
#                 lot_list = []
#                 move_list = []
#                 lot_with_qty = ""
#                 for move_line in line.move_line_ids:
#                     if move_line.lot_id:
#                         if move_line.qty_done != 0:
#                             move_list.append(move_line.lot_id.id)
#                             if not move_line.lot_id.id in lot_list:
#                                 lot_list.append(move_line.lot_id.id)
#                 for list_line in lot_list:
#                     lot_name = ''
#                     qty_done = 0
#                     lot_qty = ""
#                     for m_line in line.move_line_ids:
#                         if m_line.lot_id.id == list_line:
#                             qty_done += m_line.qty_done
#                             lot_name = m_line.lot_id.name
#                             lot_qty = lot_name + " (" + str(qty_done) + ")"
#                     if lot_with_qty:
#                         lot_with_qty += ", " + lot_qty
#                     else:
#                         lot_with_qty = lot_qty
#                 line.lot_ids_reserved = [(6, 0, move_list)]
#                 line.lot_with_qty_reserved = lot_with_qty
#         return res
#
#     def do_produce(self):
        # res = super(MrpProductProduce, self).do_produce()
        # mo_id = self.env['mrp.production'].search([('id', '=', self.production_id.id)])
        # if mo_id:
        #     for line in mo_id.move_raw_ids:
        #
        #         lot_list = []
        #         move_list = []
        #         lot_with_qty = ""
        #         for move_line in line.move_line_ids:
        #             if move_line.lot_id:
        #                 if move_line.qty_done != 0:
        #                     move_list.append(move_line.lot_id.id)
        #                     if not move_line.lot_id.id in lot_list:
        #                         lot_list.append(move_line.lot_id.id)
        #         for list_line in lot_list:
        #             lot_name = ''
        #             qty_done = 0
        #             lot_qty = ""
        #             for m_line in line.move_line_ids:
        #                 if m_line.lot_id.id == list_line:
        #                     qty_done += m_line.qty_done
        #                     lot_name = m_line.lot_id.name
        #                     lot_qty = lot_name + " (" + str(qty_done) + ")"
        #             if lot_with_qty:
        #                 lot_with_qty += ", " + lot_qty
        #             else:
        #                 lot_with_qty = lot_qty
        #         line.lot_ids_reserved = [(6, 0, move_list)]
        #         line.lot_with_qty_reserved = lot_with_qty
        # return res


#   def do_produce(self):
#         res = super(MrpProductProduce, self).do_produce()
#         mo_id = self.env['mrp.production'].search([('id', '=', self.production_id.id)])
#         if mo_id:
#             for line in mo_id.move_raw_ids:
#                 move_list = []
#                 lot_with_qty = ""
#                 for move_line in line.move_line_ids:
#                     if move_line.lot_id:
#                         if move_line.qty_done != 0:
#                             move_list.append(move_line.lot_id.id)
#                             if lot_with_qty:
#                                 lot_with_qty += ", " + move_line.lot_id.name + " (" + str(move_line.qty_done) + ")"
#                             else:
#                                 lot_with_qty = move_line.lot_id.name + " (" + str(move_line.qty_done) + ")"
#                 line.lot_ids_reserved = [(6, 0, move_list)]
#                 line.lot_with_qty_reserved = lot_with_qty
#         return res

class StockMove(models.Model):
    _inherit = "stock.move"

    stock_lot_ids = fields.Many2many('stock.production.lot', string="Suggested Lot/Serial ", copy=False)
    lot_ids_reserved = fields.Many2many('stock.production.lot', 'rel_lot_mo_ref', 'rel_move_id', 'mo_id',
                                        string="Consumed Lot/Serial", copy=False)
    lot_with_qty = fields.Char("Lot With Quantity", copy=False)
    lot_with_qty_reserved = fields.Text("Lot With Quantity", copy=False)

    def _action_assign(self):
        res = super(StockMove, self)._action_assign()
        for move in self.filtered(lambda x: x.production_id or x.raw_material_production_id):
            lot_list = []
            lot_with_qty = ""
            if move.raw_material_production_id.state not in ('to_close', 'done', 'cancel'):
                for line in move.move_line_ids:
                    if line.lot_id:
                        if lot_with_qty:
                            lot_with_qty += ", " + line.lot_id.name + " (" + str(line.quantity_product_uom) + ")"
                        else:
                            lot_with_qty = line.lot_id.name + " (" + str(line.quantity_product_uom) + ")"

                        lot_list.append(line.lot_id.id)

                move.lot_ids = [(6, 0, lot_list)]
                move.lot_with_qty = lot_with_qty
        return res
