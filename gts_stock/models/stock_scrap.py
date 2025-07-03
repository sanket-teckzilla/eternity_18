from odoo import _, api, fields, models

class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    @api.depends('company_id')
    def _compute_scrap_location_id(self):
        groups = self.env['stock.location']._read_group(
            [('company_id', 'in', self.company_id.ids), ('scrap_location', '=', True)], ['company_id'], ['id:min'])
        locations_per_company = {
            company.id: stock_warehouse_id
            for company, stock_warehouse_id in groups
        }
        for scrap in self:
            scrap.scrap_location_id = locations_per_company.get(scrap.company_id.id)