from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'


    company_registry_placeholder = fields.Char(string="Company Registry Placeholder")
