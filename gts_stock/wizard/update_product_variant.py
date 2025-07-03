import base64
import csv
import logging
from io import StringIO
from tempfile import TemporaryFile
from odoo.exceptions import UserError, ValidationError
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ImportVariant(models.TransientModel):
    _name = 'import.variant'
    _description = 'import variant'

    upload_file = fields.Binary(string='LOAD FILE')
    # prod_ref = fields.Integer()
    prod_ref = fields.Integer()

    def import_variant(self):
        csv_datas = self.upload_file
        fileobj = TemporaryFile('wb+')
        csv_datas = base64.encodebytes(csv_datas)
        fileobj.write(csv_datas)
        fileobj.seek(0)
        str_csv_data = fileobj.read().decode('utf-8')
        lis = csv.reader(StringIO(str_csv_data), delimiter=',')
        row_num = 0
        attribute_env = self.env['product.attribute']
        attribute_value_env = self.env['product.attribute.value']
        for row in lis:
            col_num = 0

            if row_num==0:
                row_num+=1
            else:

                try:
                    if row[0]:
                        external_id = str(row[0]).split("_")
                        id = external_id[6]
                        self.prod_ref = id
                    product = self.env['product.template'].search([('id', '=', self.prod_ref)])

                    for column in row:
                        if col_num == 0 or col_num == 1:
                            col_num += 1
                        else:
                            attribute = column.split(':')[0]
                            value = column.split(':')[1]
                            attribute_id = attribute_env.search([('name', '=', attribute)])
                            if not attribute_id:
                                attribute_id = attribute_env.create({
                                    'name': attribute,
                                    'value_ids': [(0, 0, {'name': value})]
                                })

                            if product :
                                attribute_found = 0
                                value_id = attribute_value_env.search([('name', '=', value),('attribute_id.id','=',attribute_id.id)])
                                for attribute_line in product.attribute_line_ids:
                                    if attribute==attribute_line.attribute_id.name:
                                        attribute_found+=1
                                        if value_id and value_id.id not in attribute_line.value_ids.ids:
                                            attribute_line.value_ids = [(4, value_id.id)]
                                        if not value_id:
                                            attribute_id.value_ids = [(0, 0, {'name': value,
                                                                               'attribute_id':attribute_id.id})]
                                            value_id = attribute_value_env.search([('name', '=', value),('attribute_id.id','=',attribute_id.id)])
                                            attribute_line.value_ids = [(4, value_id.id)]
                                if attribute_found==0:
                                    if not value_id:
                                        attribute_id.value_ids = [(0, 0, {'name': value,
                                                                          'attribute_id': attribute_id.id})]
                                    value_id = attribute_value_env.search([('name', '=', value),('attribute_id.id','=',attribute_id.id)])
                                    product.attribute_line_ids = [(0, 0, {'attribute_id': attribute_id.id,
                                                                          'value_ids': [(4, value_id.id)]})]
                            # else:
                            #     if self.prod_ref:
                            #         product = self.env['product.template'].search([('id', '=', self.prod_ref)], limit=1)
                            #         attribute_found = 0
                            #         value_id = attribute_value_env.search([('name', '=', value)])
                            #         for attribute_line in product.attribute_line_ids:
                            #             if attribute == attribute_line.attribute_id.name:
                            #                 attribute_found += 1
                            #                 if value_id and value_id.id not in attribute_line.value_ids.ids:
                            #                     attribute_line.value_ids = [(4, value_id.id)]
                            #                 if not value_id:
                            #                     attribute_id.value_ids = [(0, 0, {'name': value,
                            #                                                       'attribute_id': attribute_id.id})]
                            #                     value_id = attribute_value_env.search([('name', '=', value)])
                            #                     attribute_line.value_ids = [(4, value_id.id)]
                            #         if attribute_found == 0:
                            #             if not value_id:
                            #                 attribute_id.value_ids = [(0, 0, {'name': value,
                            #                                                   'attribute_id': attribute_id.id})]
                            #                 value_id = attribute_value_env.search([('name', '=', value)])
                            #
                            #             product.attribute_line_ids = [(0, 0, {'attribute_id': attribute_id.id,
                            #                                                   'value_ids': [(4, value_id.id)]})]
                            else:
                                raise ValidationError("Product Does not exist!")
                except Exception as e:
                    raise ValidationError(e)


