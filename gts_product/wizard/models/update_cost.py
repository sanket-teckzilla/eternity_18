import base64
import csv
import logging
from io import StringIO
from tempfile import TemporaryFile
from odoo import api, fields, models,_
from odoo.exceptions import UserError, ValidationError
import datetime

_logger = logging.getLogger(__name__)

class UpdateCost(models.TransientModel):
    _name = 'update.cost'
    _description = 'update cost'

    upload_file = fields.Binary(string='LOAD FILE')
    prod_ref = fields.Integer()

    def update_cost(self):
        csv_datas = self.upload_file
        fileobj = TemporaryFile('wb+')
        csv_datas = base64.decodebytes(csv_datas)
        fileobj.write(csv_datas)
        fileobj.seek(0)
        str_csv_data = fileobj.read().decode('utf-8')
        lis = csv.reader(StringIO(str_csv_data), delimiter=',')
        row_num = 0
        product_product = self.env['product.product']
        product_template = self.env['product.template']
        # product_template = self.env['product.template']
        for row in lis:
            col_num = 0

            if row_num==0:
                row_num+=1
            else:
                try:
                    products = False
                    if row[0]:
                        external_id = str(row[0]).split("_")
                        id = external_id[6]
                        # self.prod_ref = id
                        products = product_product.search([('product_tmpl_id.id', '=', id)])
                        if not products:
                            products = product_template.search([('id','=',id)])
                            if not products:
                                products = product_product.search([('id','=',id)])
                    # if row[1] and not products:
                    #     products = product_product.search([('product_tmpl_id.name','=',row[1])])
                    for column in row:
                        if col_num == 0 or col_num == 1:
                            col_num += 1
                        else:
                            if products and column:
                                for product in products:
                                    # product._change_standard_price(float(column.replace(',','')))
                                    # product.active = True
                                    # product.sent_for_approval = False
                                    # product.l1_approved = True
                                    if product.bom_ids:
                                        product.button_bom_cost()
                                    else:
                                        product.write({
                                            # 'standard_price_temp':float(column.replace(',','')),
                                            'standard_price':float(column.replace(',','')),
                                            'cost_updated':datetime.datetime.now()
                                        })
                                        if product.qty_available > 0 :
                                            valuation_vals = {
                                                'product_id':product.id,
                                                'value': float(column.replace(',','')) * product.qty_available,
                                                'unit_cost': float(column.replace(',','')),
                                                'quantity': product.qty_available,
                                                'remaining_qty': product.qty_available,
                                                'remaining_value': float(column.replace(',','')) * product.qty_available,
                                                'company_id':self.env.company.id,
                                                'description':"Initial Reset Entry"

                                            }
                                            self.env['stock.valuation.layer'].create(valuation_vals)

                            # elif templates:
                            #     for template in templates:
                            #         template.write({
                            #             'standard_price_temp':float(column.replace(',','')),
                            #             'standard_price':float(column.replace(',',''))
                            #         })
                except Exception as e:
                    raise ValidationError(e)

