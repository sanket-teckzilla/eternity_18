from odoo import api, fields, models, tools, _


class Users(models.Model):
    _inherit = 'res.users'

    pricelist = fields.Many2one('product.pricelist',"Price List")



