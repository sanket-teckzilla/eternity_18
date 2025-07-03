from odoo import api, fields, models, _

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    pallet_qty = fields.Float("Pallet Qty")


class ProductProduct(models.Model):
    _inherit = 'product.product'

    rfq_qty = fields.Float("RFQ Qty")
    rfq_compute = fields.Boolean()

    # def compute_rfq(self):
    #     for rec in self:
    #         purchases = self.env['purchase.order'].search


