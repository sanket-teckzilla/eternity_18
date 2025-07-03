from odoo import api, fields, models


class CountryState(models.Model):
    _description = "Country state"
    _inherit = 'res.country.state'
    _order = 'code'

    region_id = fields.Many2one('res.country.region', string='Region')


class Region(models.Model):
    _name = 'res.country.region'
    _description = 'Country Region'

    name = fields.Char('Region Name', required=True)
    description = fields.Char('Description')
    state_ids = fields.One2many('res.country.state', 'region_id', 'States')

