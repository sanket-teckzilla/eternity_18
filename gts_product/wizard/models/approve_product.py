from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ApproveProduct(models.TransientModel):
    _name = 'approve.product'
    _description = 'approve product'

    is_finished_product = fields.Boolean("Is a finished product ?")
    cost = fields.Float("Cost")


    def approve_l1(self):
        product_template = self.env['product.template'].browse(self._context['active_id'])
        # product_template.sudo().action_unarchive()
        if self.is_finished_product and product_template.bom_count == 0:
            raise UserError("Please create a BOM first !")

        # if product_template.product_variant_count > 0:
        if self.is_finished_product and product_template.bom_count > 0:
            product_template.active = True
            products = self.env['product.product'].search(
                [('product_tmpl_id', '=', product_template.id)])
            for product in products:
                product.button_bom_cost()
                product.active = True
                product.sent_for_approval = False
                product.l1_approved = True
        else:
            product_template.active = True
            products = self.env['product.product'].search(
                [('product_tmpl_id', '=', product_template.id)])
            for product in products:
                product.standard_price = self.cost
                product.active = True
                product.sent_for_approval = False
                product.l1_approved = True



