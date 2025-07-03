from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cost_updating_date = fields.Datetime("Valuation Filtering From")

    def set_values(self):
        res = super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].set_param('stock.cost_updating_date',self.cost_updating_date)
        return res

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        cost_updating_date = self.env['ir.config_parameter'].sudo().get_param('stock.cost_updating_date')
        res.update(
           cost_updating_date = cost_updating_date
        )
        return res