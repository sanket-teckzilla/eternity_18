import json

from odoo import api, fields, models, exceptions, _
from odoo.tools import float_round
from odoo.exceptions import UserError


class ReportBomStructure(models.AbstractModel):
    _inherit = 'report.mrp.report_bom_structure'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = []
        if not self.env.user.has_group('gts_so_mo_link.show_bom_structure'):
            raise exceptions.AccessError(_('You cannot print cost structure !'))
        else:
            for bom_id in docids:
                bom = self.env['mrp.bom'].browse(bom_id)
                candidates = bom.product_id or bom.product_tmpl_id.product_variant_ids
                quantity = float(data.get('quantity', 1))
                for product_variant_id in candidates:
                    if data and data.get('childs'):
                        doc = self._get_pdf_line(bom_id, product_id=product_variant_id, qty=quantity,
                                                 child_bom_ids=json.loads(data.get('childs')))
                    else:
                        doc = self._get_pdf_line(bom_id, product_id=product_variant_id, qty=quantity, unfolded=True)
                    doc['report_type'] = 'pdf'
                    doc['report_structure'] = data and data.get('report_type') or 'all'
                    docs.append(doc)
                if not candidates:
                    if data and data.get('childs'):
                        doc = self._get_pdf_line(bom_id, qty=quantity, child_bom_ids=json.loads(data.get('childs')))
                    else:
                        doc = self._get_pdf_line(bom_id, qty=quantity, unfolded=True)
                    doc['report_type'] = 'pdf'
                    doc['report_structure'] = data and data.get('report_type') or 'all'
                    docs.append(doc)
            return {
                'doc_ids': docids,
                'doc_model': 'mrp.bom',
                'docs': docs,
            }

    def _get_bom(self, bom_id=False, product_id=False, line_qty=False, line_id=False, level=False):
        bom = self.env['mrp.bom'].browse(bom_id)
        bom_quantity = line_qty
        if line_id:
            current_line = self.env['mrp.bom.line'].browse(int(line_id))
            bom_quantity = current_line.product_uom_id._compute_quantity(line_qty, bom.product_uom_id)
        # Display bom components for current selected product variant
        if product_id:
            product = self.env['product.product'].browse(int(product_id))
        else:
            product = bom.product_id or bom.product_tmpl_id.product_variant_id
        if product:
            attachments = self.env['mrp.document'].search(['|', '&', ('res_model', '=', 'product.product'),
            ('res_id', '=', product.id), '&', ('res_model', '=', 'product.template'), ('res_id', '=', product.product_tmpl_id.id)])
        else:
            product = bom.product_tmpl_id
            attachments = self.env['mrp.document'].search([('res_model', '=', 'product.template'), ('res_id', '=', product.id)])
        operations = []
        if bom.product_qty > 0:
            operations = self._get_operation_line(bom, float_round(bom_quantity / bom.product_qty, precision_rounding=1, rounding_method='UP'), 0)
        company = bom.company_id or self.env.company
        lines = {
            'bom': bom,
            'bom_qty': bom_quantity,
            'bom_prod_name': product.display_name,
            'standard_price': product.standard_price,
            'currency': company.currency_id,
            'product': product,
            'code': bom and bom.display_name or '',
            'price': product.uom_id._compute_price(product.with_context(force_company=company.id).standard_price, bom.product_uom_id) * bom_quantity,
            'total_standard_price': sum([op['total'] for op in operations]),
            'total': sum([op['total'] for op in operations]),
            'level': level or 0,
            'operations': operations,
            'operations_cost': sum([op['total'] for op in operations]),
            'attachments': attachments,
            'operations_time': sum([op['duration_expected'] for op in operations])
        }
        components, total, total_standard_price = self._get_bom_lines(bom, bom_quantity, product, line_id, level)
        lines['components'] = components
        lines['total'] += total
        lines['total_standard_price'] += company.currency_id.round(product.standard_price)
        return lines

    def _get_bom_lines(self, bom, bom_quantity, product, line_id, level):
        components = []
        total, total_standard_price = 0, 0
        for line in bom.bom_line_ids:
            line_quantity = (bom_quantity / (bom.product_qty or 1.0)) * line.product_qty
            if line._skip_bom_line(product):
                continue
            company = bom.company_id or self.env.company
            price = line.product_id.uom_id._compute_price(line.product_id.with_context(force_company=company.id).standard_price, line.product_uom_id) * line_quantity
            if line.child_bom_id:
                factor = line.product_uom_id._compute_quantity(line_quantity, line.child_bom_id.product_uom_id) / line.child_bom_id.product_qty
                sub_total = self._get_price(line.child_bom_id, factor, line.product_id)
            else:
                sub_total = price
            sub_total = self.env.company.currency_id.round(sub_total)
            components.append({
                'prod_id': line.product_id.id,
                'prod_name': line.product_id.display_name,
                'code': line.child_bom_id and line.child_bom_id.display_name or '',
                'prod_qty': line_quantity,
                'prod_uom': line.product_uom_id.name,
                'standard_price': line.product_id.standard_price,
                'prod_cost': company.currency_id.round(price),
                'parent_id': bom.id,
                'line_id': line.id,
                'level': level or 0,
                'total': sub_total,
                'child_bom': line.child_bom_id.id,
                'phantom_bom': line.child_bom_id and line.child_bom_id.type == 'phantom' or False,
                'attachments': self.env['mrp.document'].search(['|', '&',
                    ('res_model', '=', 'product.product'), ('res_id', '=', line.product_id.id), '&', ('res_model', '=', 'product.template'), ('res_id', '=', line.product_id.product_tmpl_id.id)]),

            })
            total += sub_total
            total_standard_price += line.product_id.standard_price
        return components, total, total_standard_price

    def _get_pdf_line(self, bom_id, product_id=False, qty=1, child_bom_ids=[], unfolded=False):

        def get_sub_lines(bom, product_id, line_qty, line_id, level):
            data = self._get_bom(bom_id=bom.id, product_id=product_id.id, line_qty=line_qty, line_id=line_id, level=level)
            bom_lines = data['components']
            lines = []
            for bom_line in bom_lines:
                lines.append({
                    'name': bom_line['prod_name'],
                    'type': 'bom',
                    'quantity': bom_line['prod_qty'],
                    'uom': bom_line['prod_uom'],
                    'standard_price': bom_line['standard_price'],
                    'prod_cost': bom_line['prod_cost'],
                    'bom_cost': bom_line['total'],
                    'level': bom_line['level'],
                    'code': bom_line['code'],
                    'child_bom': bom_line['child_bom'],
                    'prod_id': bom_line['prod_id']
                })
                if bom_line['child_bom'] and (unfolded or bom_line['child_bom'] in child_bom_ids):
                    line = self.env['mrp.bom.line'].browse(bom_line['line_id'])
                    lines += (get_sub_lines(line.child_bom_id, line.product_id, bom_line['prod_qty'], line, level + 1))
            if data['operations']:
                lines.append({
                    'name': _('Operations'),
                    'type': 'operation',
                    'quantity': data['operations_time'],
                    'uom': _('minutes'),
                    'bom_cost': data['operations_cost'],
                    'level': level,
                })
                for operation in data['operations']:
                    if unfolded or 'operation-' + str(bom.id) in child_bom_ids:
                        lines.append({
                            'name': operation['name'],
                            'type': 'operation',
                            'quantity': operation['duration_expected'],
                            'uom': _('minutes'),
                            'bom_cost': operation['total'],
                            'level': level + 1,
                        })
            return lines

        bom = self.env['mrp.bom'].browse(bom_id)
        product = product_id or bom.product_id or bom.product_tmpl_id.product_variant_id
        data = self._get_bom(bom_id=bom_id, product_id=product.id, line_qty=qty)
        pdf_lines = get_sub_lines(bom, product, qty, False, 1)
        data['components'] = []
        data['lines'] = pdf_lines
        return data
