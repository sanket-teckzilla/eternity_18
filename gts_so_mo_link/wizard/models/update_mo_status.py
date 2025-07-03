from odoo import api, models, fields, _
from odoo.exceptions import UserError
import base64
import csv
from io import StringIO
from tempfile import TemporaryFile

class UpdateMO(models.TransientModel):
    _name = 'cancel.mo'
    _description = 'Cancel MO'


    upload_file = fields.Binary("Upload File")

    def close_mo(self):
        csv_datas = self.upload_file
        fileobj = TemporaryFile('wb+')
        csv_datas = base64.decodebytes(csv_datas)
        fileobj.write(csv_datas)
        fileobj.seek(0)
        str_csv_data = fileobj.read().decode('utf-8')
        lis = csv.reader(StringIO(str_csv_data), delimiter=',')
        row_num = 0

        # warehouse = self.env['stock.warehouse'].search(
        #     [('company_id', '=', self.env.company.id)], limit=1
        # )
        qty_index =[8]
        rows_to_exclude = [0,1,2]
        lot_index =[]
        for row in lis:
            if row_num in rows_to_exclude:
                row_num+=1
            else:
                if str(row[10]) == 'CLOSED':
                    mo = self.env['mrp.production'].search([('name', '=', row[1])])
                    mo.state = 'done'