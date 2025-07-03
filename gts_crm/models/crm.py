from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Lead(models.Model):
    _inherit = "crm.lead"

    def write(self, values):
        res = super(Lead, self).write(values)
        if 'default_type' in self.env.context and self.env.context['default_type'] == 'opportunity':
            if self.expected_revenue <= 0:
                raise UserError(_('Expected Revenue cannot be Zero!'))
        return res


    def create(self, values):
        if values.get('type') == 'opportunity' and 'expected_revenue' in values:
            if values.get('expected_revenue') <= 0:
                raise UserError(_('Expected Revenue cannot be Zero!'))
        rec = super(Lead, self).create(values)
        return rec

    # def create(self, values):
    #     if values.get('type') == 'opportunity' and values.get('expected_revenue') is not None:
    #         if values['expected_revenue'] <= 0:
    #             raise UserError(_('Expected Revenue must be greater than zero!'))
    #     rec = super(Lead, self).create(values)
    #     return rec

