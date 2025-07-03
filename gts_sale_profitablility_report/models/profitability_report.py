from odoo import tools
from odoo import api, fields, models


class ProfitabilityReport(models.Model):
    _name = "profitability.report"
    _description = "Profitability Report"
    _custom = False
    _auto = False

    confirmation_date = fields.Datetime("Order Date")
    region = fields.Char("Region")
    cost_per_ah = fields.Float('SP / AH')
    margin_cost = fields.Float('Margin')
    amount_total = fields.Float('Total Cost')
    user_id = fields.Many2one('res.users', 'Salesperson')
    partner_id = fields.Many2one('res.partner', 'Customer')
    reference = fields.Many2one('sale.order', 'Reference')
    amount_untaxed = fields.Float('Total Selling Price')

    def _query_to_data(self):
        query = """  select row_number() OVER () AS id,
                       so.date_order as confirmation_date,
                       so.total_purchase_price as amount_total,
                       so.amount_untaxed as amount_untaxed,
                       so.cost_per_ah as cost_per_ah,
                       so.user_id as user_id,
                       so.partner_id as partner_id,
                       so.margin  as margin_cost,
                       so.id as reference,
                       rcr.name as region
                       from sale_order as so
                       inner join res_partner as rp on so.partner_id = rp.id
                       inner join res_country_region as rcr on rp.region_id = rcr.id
                       inner join res_users as ru on so.user_id = ru.id
                       where so.state = 'sale'
                       """
        return query

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # self.env.cr.execute("""CREATE or REPLACE VIEW %s as (%s)""" % (self._table, self._query_to_data()))
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (%s)""" % (self._table, self._query_to_data()))
