
from odoo import api, fields, models, _

class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.depends('picking_ids')
    def _compute_picking_ids(self):
        for order in self:
            deliveries = self.env['stock.picking'].sudo().search([('origin', '=', order.name),('picking_type_id.code','=','outgoing')])
            for delv in deliveries:
                if delv.id not in order.picking_ids.ids:
                    order.picking_ids = [(4,delv.id)]

            order.delivery_count = len(order.picking_ids)
