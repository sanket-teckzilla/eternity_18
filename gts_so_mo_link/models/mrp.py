from odoo import api, fields, models, exceptions, _
import qrcode
import base64
from io import BytesIO
from datetime import datetime,date, timedelta
# from odoo.tools import float_compare, float_round, float_is_zero, format_datetime
from collections import defaultdict
from odoo.exceptions import UserError


class MRPProduction(models.Model):
    _inherit = "mrp.production"

    partner_id = fields.Many2one('res.partner', string='Customer')
    untaxed_amount_updated = fields.Boolean(compute='_compute_untaxed_amount')
    untaxed_amount = fields.Float('Untaxed Amount')
    client_order_ref = fields.Char('Order Reference/ PO')
    delivery_date = fields.Datetime('Delivery Date')
    lot_numbers_count = fields.Integer('Lot Count', compute="_compute_lot_numbers", default=0, copy=False)
    test_certificate_count = fields.Integer('Lot Count', compute="_compute_test_certificates", default=0, copy=False)
    test_report_ids = fields.One2many('test.report.mo', 'production_id', string='Test Certificate Lines')
    attach_production_report = fields.Binary('Attach Production Report', compute='_attachment_name',
                                             inverse='_set_filename', copy=False)
    attach_production_report_name = fields.Char('Attach Production Report')
    pdf_attachment_id = fields.Many2one('ir.attachment', copy=False)
    rate_on_sample_cell = fields.Float('Rate Obtained on Sample Cell')
    product_type = fields.Selection(related='product_id.product_type')
    so_id = fields.Many2one('sale.order')
    product_id = fields.Many2one(
        'product.product', 'Product',
        domain="""[
                    ('type', 'in', ['product', 'consu']),
                    '|',
                        ('company_id', '=', False),
                        ('company_id', '=', company_id)
                ]
                """,
        readonly=True, required=True, check_company=True,
        states={'draft': [('readonly', False)]})

    so_id = fields.Many2one('sale.order',"Sale Order")
    region = fields.Many2one('res.country.region',"Region")
    sales_person = fields.Many2one('res.users',"Sales Person")
    cost_per_ah = fields.Float("Cost Per AH")

    @api.depends('finished_move_line_ids', 'finished_move_line_ids.lot_id')
    def _compute_lot_numbers(self):
        for rec in self:
            rec.lot_numbers_count = 0
            for lines in rec.finished_move_line_ids:
                if lines.lot_id.id:
                    rec.lot_numbers_count += 1

    @api.depends('origin')
    def _compute_untaxed_amount(self):
        for rec in self:
            if rec.origin:
               so_rel = self.env['sale.order'].search([('name','=',rec.origin)],limit=1)
               # c = CurrencyRates()
               # rate = c.get_rate(so_rel.pricelist_id.currency_id.name, 'INR')
               untaxed_amount = 0.0
               for line in so_rel.order_line:
                   if line.product_id.id == rec.product_id.id:
                       untaxed_amount += line.price_unit
                       rec.cost_per_ah = line.cost_per_ah
                       # untaxed_amount += line.price_unit * rate

               rec.untaxed_amount_updated = True
               if rec.state not in ('done','cancel'):
                   rec.untaxed_amount = untaxed_amount * rec.product_qty
               else:
                   rec.untaxed_amount = 0.0

               rec.so_id = so_rel.id
               rec.region = so_rel.partner_id.region_id.id
               rec.sales_person = so_rel.user_id.id
               rec.so_id = so_rel.id
               rec.client_order_ref = so_rel.po_number
               rec.delivery_date = so_rel.commitment_date if not rec.delivery_date else rec.delivery_date
               rec.partner_id = so_rel.partner_id.id
            else:
                rec.untaxed_amount_updated = False


    # @api.depends('origin')
    # def _compute_untaxed_amount(self):
    #     for rec in self:
    #         if rec.origin:
    #            so_rel = self.env['sale.order.line'].search([('order_id.name','=',rec.origin),('product_id','=',rec.product_id.id)],limit=1)
    #            untaxed_amount = 0.0
    #
    #            untaxed_amount += so_rel.price_unit
    #            # rec.delivery_date = so_rel.commitment_date if not rec.delivery_date else rec.delivery_date
    #
    #            rec.untaxed_amount_updated = True
    #            if rec.state not in ('done','cancel'):
    #                rec.untaxed_amount = untaxed_amount * rec.product_qty
    #            else:
    #                rec.untaxed_amount = 0.0
    #            rec.client_order_ref = so_rel.order_id.po_number
    #            rec.delivery_date = so_rel.del_date if not rec.delivery_date else rec.delivery_date
    #            rec.partner_id = so_rel.order_id.partner_id.id
    #         else:
    #             rec.untaxed_amount_updated = False

    def action_view_lot_numbers(self):
        action = self.env.ref('stock.action_production_lot_form').read()[0]
        list_ids = []
        for lines in self.finished_move_line_ids:
            if lines.lot_id.id:
                list_ids.append(lines.lot_id.id)
        action['domain'] = [('id', 'in', list_ids)]
        action['context'] = {'create': False}
        return action

    @api.depends('test_report_ids')
    def _compute_test_certificates(self):
        for rec in self:
            rec.test_certificate_count = 0
            for lines in rec.test_report_ids:
                rec.test_certificate_count += 1

    def action_view_test_certificate(self):
        action = self.env.ref('gts_so_mo_link.action_view_test_report').read()[0]
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    def action_generate_serial(self):
        self.ensure_one()
        if self.product_id.product_type == 'battery':
            mnth = datetime.today().strftime('%m')
            year = datetime.today().strftime('%Y')
            a_length = len(year)
            year_ = year[a_length - 2: a_length]
            dict = {'0': 'M', '1': 'O', '2': 'T', '3': 'H', '4': 'E', '5': 'R', '6': 'L', '7': 'A', '8': 'N', '9': 'D'}
            list_, name = [], ''
            nxt_number = self.env['ir.sequence'].next_by_code('stock.lot.serial')
            for a in year_:
                list_.append(dict[a])
                name = ''.join(str(v) for v in list_)
            sequence = "ET-" + str(mnth) + "-" + name + "-" + nxt_number
            self.lot_producing_id = self.env['stock.lot'].create({
                'product_id': self.product_id.id,
                'company_id': self.company_id.id,
                'name': sequence

            })
        else:
            self.lot_producing_id = self.env['stock.lot'].create({
                'product_id': self.product_id.id,
                'company_id': self.company_id.id
            })
        if self.move_finished_ids.filtered(lambda m: m.product_id == self.product_id).move_line_ids:
            self.move_finished_ids.filtered(lambda m: m.product_id == self.product_id).move_line_ids.lot_id = self.lot_producing_id
        if self.product_id.tracking == 'serial':
            self._set_qty_producing()

    @api.depends('attach_production_report')
    def _attachment_name(self):
        val = self.pdf_attachment_id.datas or ''
        self.attach_production_report = val or ''

    def _set_filename(self):
        Attachment = self.env['ir.attachment']
        attachment_value = {
            'name': self.attach_production_report_name or '',
            'datas': self.attach_production_report or '',
            # 'datas_fname': self.attach_production_report_name or '',
            'type': 'binary',
            'res_model': "mrp.production",
            'res_id': self.id,
        }
        attachment = Attachment.sudo().create(attachment_value)
        self.pdf_attachment_id = attachment.id or ''

    # def open_produce_product(self):
    #     for raw in self.move_raw_ids:
    #         if raw.product_id.qty_available < raw.product_uom_qty:
    #             raise UserError(_("Quantity on hand and quantity to consume does not match for the components !"))
    #
    #     res = super(MRPProduction, self).open_produce_product()
    #     return  res
    #
    #
    # def button_mark_done(self):
    #     for raw in self.move_raw_ids:
    #         if raw.product_id.qty_available < raw.product_uom_qty:
    #             raise UserError(_("Quantity on hand and quantity to consume does not match for the components !"))
    #     res = super(MRPProduction, self).button_mark_done()
    #     return res


        # if not self.attach_production_report:
        #     raise UserError(_('Please attach Production Report!'))

    def button_mark_done(self):
        ###Custom Code####

        for production in self:
            for raw in production.move_raw_ids:
                if raw.product_id.tracking=='lot' and not raw.lot_ids:
                    raise UserError(_("Please provide a lot to the cell component !"))

        missing_move_vals = {}
        move_vals=[]
        for production in self:
            for raw in production.move_raw_ids:
                if raw.product_id.tracking == 'lot':
                    tot_quantity =0
                    # for lot in raw.finished_lot_ids:
                    #     tot_quantity+= lot.product_qty
                    # if tot_quantity < raw.product_uom_qty / production.product_qty:
                    #     raise UserError(_('The lots provided does not have enough quantity to produce!'))
                    missing_move_vals = {
                        'name': production.name,
                        'product_id': raw.product_id.id,
                        'raw_material_production_id': production.id,
                        'product_uom': raw.product_id.uom_id.id,
                        # 'unit_factor':product_uom_qty,
                        # 'quantity_done': raw.product_uom_qty/production.product_qty,
                        'quantity': raw.custom_product_uom_qty,
                        'lot_ids': raw.lot_ids,
                        'location_dest_id': raw.location_dest_id.id,
                        'location_id': raw.location_id.id
                    }
                    move_vals.append(missing_move_vals)

        self._button_mark_done_sanity_checks()
        if not self.env.context.get('button_mark_done_production_ids'):
            self = self.with_context(button_mark_done_production_ids=self.ids)

        # res = self._pre_button_mark_done()
        res = self.pre_button_mark_done()

        if res is not True:
            return res

        if self.env.context.get('mo_ids_to_backorder'):
            productions_to_backorder = self.browse(self.env.context['mo_ids_to_backorder'])
            productions_not_to_backorder = self - productions_to_backorder
        else:
            productions_not_to_backorder = self
            productions_to_backorder = self.env['mrp.production']

        ##Custom Code###########################
        for production in self:
            # if production not in productions_to_backorder:
            for move in move_vals:
                missing_move = self.env['stock.move'].create(move)
                if missing_move.lot_ids:
                    for move_line in missing_move.mapped('move_line_ids'):
                        move_line.lot_id = missing_move.lot_ids.id
                        move_line.lot_name = missing_move.lot_ids.name
                missing_move._action_confirm()
                production.move_raw_ids = [(0,production.id,move)]
                        # missing_move._action_done(cancel_backorder=False)

        self.workorder_ids.button_finish()

        productions_not_to_backorder._post_inventory(cancel_backorder=True)
        productions_to_backorder._post_inventory(cancel_backorder=False)
        backorders = productions_to_backorder._generate_backorder_productions()

        # if completed products make other confirmed/partially_available moves available, assign them
        done_move_finished_ids = (productions_to_backorder.move_finished_ids | productions_not_to_backorder.move_finished_ids).filtered(lambda m: m.state == 'done')
        done_move_finished_ids._trigger_assign()


        # Moves without quantity done are not posted => set them as done instead of canceling. In
        # case the user edits the MO later on and sets some consumed quantity on those, we do not
        # want the move lines to be canceled.
        (productions_not_to_backorder.move_raw_ids | productions_not_to_backorder.move_finished_ids).filtered(lambda x: x.state not in ('done', 'cancel')).write({
            'state': 'done',
            'product_uom_qty': 0.0,
        })

        for production in self:
            production.write({
                'date_finished': fields.Datetime.now(),
                'product_qty': production.qty_produced,
                'priority': '0',
                'is_locked': True,
            })

        for workorder in self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')):
            workorder.duration_expected = workorder._get_duration_expected()

        ####Custom code##############################

        if not self.attach_production_report:
            raise UserError(_('Please attach Production Report!'))
        lot_id = ''
        if self.lot_producing_id:
            lot_id = self.lot_producing_id.id
            # Test Certificate attach in lot
            # action = self.env.ref('gts_so_mo_link.single_action_report_test_certificate_mrp').render_qweb_pdf(
            #     self.finished_lot_id.id)[0]
            # pdf = base64.b64encode(action)
            # attachment = self.env['ir.attachment'].create({
            #     'name': 'Test Certificate ' + self.finished_lot_id.name,
            #     'datas': pdf,
            #     'res_model': 'mrp.product.produce',
            #     'res_id': self.id,
            #     'type': 'binary',
            # })
            # self.finished_lot_id.test_report = attachment.datas
            # self.finished_lot_id.test_report_name = attachment.name
            self.lot_producing_id.used_lot = True
        stock_move_line = self.env['stock.move.line'].search([('lot_id', '=', self.lot_producing_id.id),
                                                              ('reference', '=', self.name)], limit=1)
        if stock_move_line and self.attach_production_report:
            stock_move_line.pdf_attachment_id = self.pdf_attachment_id.id or ''
            stock_move_line.attach_production_report = self.pdf_attachment_id.datas or ''
            stock_move_line.attach_production_report_name = self.pdf_attachment_id.name or ''
        else:
            stock_move_line = self.env['stock.move.line'].search([('reference', '=', self.name),
                                                                  ('attach_production_report', '=', None)], limit=1)
            if stock_move_line and self.attach_production_report:
                stock_move_line.pdf_attachment_id = self.pdf_attachment_id.id or ''
                stock_move_line.attach_production_report = self.pdf_attachment_id.datas or ''
                stock_move_line.attach_production_report_name = self.pdf_attachment_id.name or ''
        if self.lot_producing_id and self.attach_production_report:
            self.lot_producing_id.pdf_attachment_id = self.pdf_attachment_id.id or ''
            self.lot_producing_id.attach_production_report = self.pdf_attachment_id.datas or ''
            self.lot_producing_id.attach_production_report_name = self.pdf_attachment_id.name or ''
        stock_moves = self.env['stock.move'].search([('raw_material_production_id', '=', self.id),
                                                    ('product_id.product_type', '=', 'cell'),
                                                    ('product_uom_qty', '>', 0)])
        volts = int(self.product_id.volts)
        ah = int(self.product_id.ah)
        qty, product_name = 0,''
        no_of_cell_type = ""
        if stock_moves:
            for stock_move in stock_moves:
                qty += int((stock_move.product_uom_qty / self.product_qty) * self.qty_producing)
                product_name = stock_move.product_id.name
            no_of_cell_type = str(qty) + " x " + product_name



        battery_type = str(volts) + " V " + str(ah) + " AH  (" + no_of_cell_type + ")"

        # rated_capacity = str(volts) + " V " + str(ah) + " AH"
        rate_on_sample_cell = str(ah) + " Ah"
        test_date = None

        if self.origin:
            invoice = self.env['account.move'].search(
                [('invoice_origin', '=', self.origin), ('state', '!=', 'cancel')], limit=1,
                order='create_date desc')
            if invoice:
                # test_date = invoice.invoice_date
                test_date = self.delivery_date
        test_report_dict = {
            'battery_type': battery_type,
            'volts': volts,
            'ah': ah,
            # 'rated_capacity': rated_capacity,
            'rate_on_sample_cell': self.rate_on_sample_cell or 0,
            'production_id': self.id,
            'lot_id': lot_id,
            'date': test_date or date.today(),
            'qty_produced': self.qty_producing,
            'no_of_cell_type': no_of_cell_type
        }
        test_report_id = self.env['test.report.mo'].create(test_report_dict)
        if self.lot_producing_id:
            self.lot_producing_id.test_report_id = test_report_id.id

    ######################################################################
        # if not backorders:
        for production in self:
            for raw in production.move_raw_ids:
                if raw.quantity == 0 and raw.product_id.tracking == 'lot':
                    for line in raw.mapped('move_line_ids'):
                        line.write({'state': 'draft'})
                        line.unlink()
                    raw.write({'state': 'draft'})
                    raw.unlink()
            # for production in self:
            #     for raw in production.move_raw_ids:
            #         if raw.quantity_done == 0 and raw.product_id.tracking == 'lot':
            #             self.env.cr.execute("delete from stock_move where id=%s", [raw.id, ])
            if self.env.context.get('from_workorder'):
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'mrp.production',
                    'views': [[self.env.ref('mrp.mrp_production_form_view').id, 'form']],
                    'res_id': self.id,
                    'target': 'main',
                }
            return True

        context = self.env.context.copy()
        context = {k: v for k, v in context.items() if not k.startswith('default_')}
        for k, v in context.items():
            if k.startswith('skip_'):
                context[k] = False
        action = {
            'res_model': 'mrp.production',
            'type': 'ir.actions.act_window',
            'context': dict(context, mo_ids_to_backorder=None)
        }
        if len(backorders) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': backorders[0].id,
            })
        else:
            action.update({
                'name': _("Backorder MO"),
                'domain': [('id', 'in', backorders.ids)],
                'view_mode': 'list,form',
            })

        return action


    def _generate_backorder_productions(self, close_mo=True):
        backorders = self.env['mrp.production']
        for production in self:
            if production.backorder_sequence == 0:  # Activate backorder naming
                production.backorder_sequence = 1
            backorder_mo = production.copy(default=production._get_backorder_mo_vals())
            if close_mo:
                # continue
                production.move_raw_ids.filtered(lambda m: m.state not in ('done','draft','cancel')).write({
                    'raw_material_production_id': backorder_mo.id,
                })
                production.move_finished_ids.filtered(lambda m: m.state not in ('done','cancel')).write({
                    'production_id': backorder_mo.id,
                })
            else:
                new_moves_vals = []
                for move in production.move_raw_ids | production.move_finished_ids:
                    if not move.additional:
                        qty_to_split = move.product_uom_qty - move.unit_factor * production.qty_producing
                        qty_to_split = move.product_uom._compute_quantity(qty_to_split, move.product_id.uom_id, rounding_method='HALF-UP')
                        move_vals = move._split(qty_to_split)
                        if not move_vals:
                            continue
                        if move.raw_material_production_id:
                            move_vals[0]['raw_material_production_id'] = backorder_mo.id
                        else:
                            move_vals[0]['production_id'] = backorder_mo.id
                        new_moves_vals.append(move_vals[0])
                new_moves = self.env['stock.move'].create(new_moves_vals)

            backorders |= backorder_mo

            for old_wo, wo in zip(production.workorder_ids, backorder_mo.workorder_ids):
                wo.qty_produced = max(old_wo.qty_produced - old_wo.qty_producing, 0)
                if wo.product_tracking == 'serial':
                    wo.qty_producing = 1
                else:
                    wo.qty_producing = wo.qty_remaining
                if wo.qty_producing == 0:
                    wo.action_cancel()

            production.name = self._get_name_backorder(production.name, production.backorder_sequence)

            # We need to adapt `duration_expected` on both the original workorders and their
            # backordered workorders. To do that, we use the original `duration_expected` and the
            # ratio of the quantity really produced and the quantity to produce.
            ratio = production.qty_producing / production.product_qty
            for workorder in production.workorder_ids:
                workorder.duration_expected = workorder.duration_expected * ratio
            for workorder in backorder_mo.workorder_ids:
                workorder.duration_expected = workorder.duration_expected * (1 - ratio)

        # As we have split the moves before validating them, we need to 'remove' the excess reservation
        if not close_mo:
            self.move_raw_ids.filtered(lambda m: not m.additional)._do_unreserve()
            self.move_raw_ids.filtered(lambda m: not m.additional)._action_assign()
        # Confirm only productions with remaining components
        backorders.filtered(lambda mo: mo.move_raw_ids).action_confirm()
        backorders.filtered(lambda mo: mo.move_raw_ids).action_assign()

        for production in self:
            for raw in production.move_raw_ids:
                if raw.quantity == 0 and raw.product_id.tracking == 'lot':
                    for line in raw.mapped('move_line_ids'):
                        line.write({'state': 'draft'})
                        line.unlink()
                    raw.write({'state':'draft'})
                    raw.unlink()
        # Remove the serial move line without reserved quantity. Post inventory will assigned all the non done moves
        # So those move lines are duplicated.
        backorders.move_raw_ids.move_line_ids.filtered(lambda ml: ml.product_id.tracking == 'serial' and ml.product_qty == 0).unlink()
        backorders.move_raw_ids._recompute_state()

        return backorders


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    sent_for_approval = fields.Boolean()

    @api.model_create_multi
    def create(self,vals):
        user = self.env.user
        res = super(MrpBom, self).create(vals)
        params = {}
        if 'params' in self.env.context:
            params = self.env.context['params']
        else:
            params['model'] = ''
        model = params['model']
        if (model == 'mrp.bom' and not 'active_model' in self.env.context) or self.env.context.get('active_model') == 'product.template':
            if not user.has_group('gts_so_mo_link.bom_approver'):
                res['active'] = False
                res['sent_for_approval'] = True
                message = """<p><b>""" + str(user.name) + """</b> has requested to approve BOM <b>""" + res.display_name + """</b>.</p>"""
                users = self.env['res.users'].search([])
                for auth_user in users:
                    if auth_user.has_group('gts_so_mo_link.bom_approver'):
                        email_vals = {
                            'subject': """BOM Approval Request""",
                            'email_to': auth_user.name,
                            'email_from': user.name,
                            'reply_to': self.env.user.partner_id.email,
                            'body_html': message
                        }
                        email = self.env['mail.mail'].sudo().create(email_vals)
                        email.send()
        return res

    @api.onchange('bom_line_ids','product_qty','product_tmpl_id','product_id')
    def _send_to_approve(self):
        user = self.env.user
        # for rec in self:
        #     if not user.has_group('gts_so_mo_link.bom_approver'):
        #         rec.sent_for_approval = True
        #         rec.active = False
        #         message = """<p><b>""" + str(user.name) + """</b> has requested to approve BOM <b>""" + self.display_name + """</b>.</p>"""
        #         # message = """<p><b>""" + str(user.name) + """</b> has requested to approve BOM .</p>"""
        #         users = self.env['res.users'].search([])
        #         for auth_user in users:
        #             if auth_user.has_group('gts_so_mo_link.bom_approver'):
        #                 email_vals = {
        #                     'subject': """BOM Approval Request""",
        #                     'email_to': auth_user.name,
        #                     'email_from': user.name,
        #                     'reply_to': self.env.user.partner_id.email,
        #                     'body_html': message
        #                 }
        #                 email = self.env['mail.mail'].sudo().create(email_vals)
        #                 email.send()

        if not user.has_group('gts_so_mo_link.bom_approver'):
            self.product_tmpl_id.sent_for_approval = True
            self.product_tmpl_id.l1_approved = False
            self.product_tmpl_id.active = False

    def write(self,vals):
        user = self.env.user
        params = {}
        # vals['product_tmpl_id'] = self.product_tmpl_id
        active_id = False
        id = False
        do_not_write = False
        if 'params' in self.env.context:
            params = self.env.context['params']
            active_id = params['active_id'] if 'active_id' in params else False
            id = params['id'] if 'id' in params else False
        else:
            params['model'] = ''

        model = params['model']
        if (active_id and id ) and active_id == id:
            do_not_write = True
        if (model == 'mrp.bom' or self.env.context.get('active_model') == 'product.template') and do_not_write == False:
            if not user.has_group('gts_so_mo_link.bom_approver'):
                vals['active'] = False
                vals['sent_for_approval'] = True
                # message = """<p><b>""" + str(user.name) + """</b> has requested to approve BOM <b>""" + self.display_name + """</b>.</p>"""
                message = """<p><b>""" + str(user.name) + """</b> has requested to approve BOM .</p>"""
                users = self.env['res.users'].search([])
                for auth_user in users:
                    if auth_user.has_group('gts_so_mo_link.bom_approver'):
                        email_vals = {
                            'subject': """BOM Approval Request""",
                            'email_to': auth_user.name,
                            'email_from': user.name,
                            'reply_to': self.env.user.partner_id.email,
                            'body_html': message
                        }
                        email = self.env['mail.mail'].sudo().create(email_vals)
                        email.send()
        return super(MrpBom, self).write(vals)

    def approve_bom(self):
        for rec in self:
            rec.sent_for_approval = False
            rec.active = True


class MrpUnbuild(models.Model):
    _inherit = 'mrp.unbuild'

    def action_unbuild(self):
        self.ensure_one()
        self._check_company()
        if self.product_id.tracking != 'none' and not self.lot_id.id:
            raise UserError(_('You should provide a lot number for the final product.'))

        if self.mo_id:
            if self.mo_id.state != 'done':
                raise UserError(_('You cannot unbuild a undone manufacturing order.'))

        consume_moves = self._generate_consume_moves()
        consume_moves._action_confirm()
        produce_moves = self._generate_produce_moves()
        produce_moves._action_confirm()

        finished_moves = consume_moves.filtered(lambda m: m.product_id == self.product_id)
        consume_moves -= finished_moves

        if any(produce_move.has_tracking != 'none' and not self.mo_id for produce_move in produce_moves):
            raise UserError(_('Some of your components are tracked, you have to specify a manufacturing order in order to retrieve the correct components.'))

        if any(consume_move.has_tracking != 'none' and not self.mo_id for consume_move in consume_moves):
            raise UserError(_('Some of your byproducts are tracked, you have to specify a manufacturing order in order to retrieve the correct byproducts.'))

        for finished_move in finished_moves:
            if finished_move.has_tracking != 'none':
                self.env['stock.move.line'].create({
                    'move_id': finished_move.id,
                    'lot_id': finished_move.lot_ids.id if finished_move.lot_ids else self.lot_id.id,
                    'quantity': finished_move.product_uom_qty,
                    'product_id': finished_move.product_id.id,
                    'product_uom_id': finished_move.product_uom.id,
                    'location_id': finished_move.location_id.id,
                    'location_dest_id': finished_move.location_dest_id.id,
                })
            else:
                finished_move.quantity = finished_move.product_uom_qty

        # TODO: Will fail if user do more than one unbuild with lot on the same MO. Need to check what other unbuild has aready took
        for move in produce_moves | consume_moves:
            if move.has_tracking != 'none' or move.has_tracking != 'lot' :
                original_move = move in produce_moves and self.mo_id.move_raw_ids or self.mo_id.move_finished_ids
                original_move = original_move.filtered(lambda m: m.product_id == move.product_id)
                needed_quantity = move.product_uom_qty
                moves_lines = original_move.mapped('move_line_ids')

                # if move in produce_moves and self.lot_id:
                #     moves_lines = moves_lines.filtered(lambda ml: self.lot_id in ml.produce_line_ids.lot_id)  # FIXME sle: double check with arm

                for move_line in moves_lines:
                    # Iterate over all move_lines until we unbuilded the correct quantity.
                    taken_quantity = min(needed_quantity, move_line.quantity)
                    if taken_quantity:
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'lot_id': move.lot_ids.id if move.lot_ids else move_line.lot_id.id,
                            'quantity': taken_quantity,
                            'product_id': move.product_id.id,
                            'product_uom_id': move_line.product_uom_id.id,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                        })
                        needed_quantity -= taken_quantity
            else:
                move.quantity = move.product_uom_qty

        finished_moves._action_done()
        consume_moves._action_done()
        produce_moves._action_done()
        produced_move_line_ids = produce_moves.mapped('move_line_ids').filtered(lambda ml: ml.quantity > 0)
        consume_moves.mapped('move_line_ids').write({'produce_line_ids': [(6, 0, produced_move_line_ids.ids)]})

        return self.write({'state': 'done'})


class TestCertificateMO(models.AbstractModel):
    _name = "report.gts_so_mo_link.report_mrp_test_certificate"
    _description = 'Mrp Certificate'

    def _get_report_values(self, docids, data=None):
        docs = self.env['mrp.production'].browse(docids)
        for doc in docs:
            if not doc.finished_move_line_ids:
                raise exceptions.AccessError(_('You Cannot print Test Certificate as there is no Quantity Produced !'))
            if doc.state == 'cancel':
                raise exceptions.AccessError(_('You can not print a Test Certificate for a cancelled Manufacturing Order!'))
            if not doc.test_report_ids:
                raise exceptions.AccessError(_('Test Certificate has not been generated yet!'))
        return {
            'doc_ids': docs.ids,
            'doc_model': 'mrp.production',
            'docs': docs,
        }


class TestCertificateMOWithoutHF(models.AbstractModel):
    _name = "report.gts_so_mo_link.report_mrp_without_hf_test_certificate"
    _description = 'Test Certificate'

    def _get_report_values(self, docids, data=None):
        docs = self.env['mrp.production'].browse(docids)
        for doc in docs:
            if not doc.finished_move_line_ids:
                raise exceptions.AccessError(_('You Cannot print Test Certificate as there is no Quantity Produced !'))
            if doc.state == 'cancel':
                raise exceptions.AccessError(_('You can not print a Test Certificate for a cancelled Manufacturing Order!'))
            if not doc.test_report_ids:
                raise exceptions.AccessError(_('Test Certificate has not been generated yet!'))
        return {
            'doc_ids': docs.ids,
            'doc_model': 'mrp.production',
            'docs': docs,
        }


class QRReportMOCurrent(models.AbstractModel):
    _name = "report.gts_so_mo_link.report_mrp_production_qrcode"
    _description = 'Qrcode'

    def _get_report_values(self, docids, data=None):
        docs = self.env['mrp.production'].browse(docids)
        for doc in docs:
            if not doc.finished_move_line_ids:
                raise exceptions.AccessError(_('You Cannot print QR Code as there is no Quantity Produced !'))
            if doc.state == 'cancel':
                raise exceptions.AccessError(_('You can not print QR Report for a Cancelled Manufacturing Order !'))
            for data in doc.finished_move_line_ids:
                if not data.lot_id:
                    raise exceptions.AccessError(_('You can not print QR Code as no Serial Number has been provided!'))
        return {
            'doc_ids': docs.ids,
            'doc_model': 'mrp.production',
            'docs': docs,
        }


class QRReportMOUpcoming(models.AbstractModel):
    _name = "report.gts_so_mo_link.report_mrp_production_qrcode_upcoming"
    _description = 'report_mrp_production_qrcode_upcoming'

    def _get_report_values(self, docids, data=None):
        docs = self.env['mrp.production'].browse(docids)
        for doc in docs:
            if not doc.finished_move_line_ids:
                raise exceptions.AccessError(_('You Cannot print QR Code as there is no Quantity Produced !'))
            if doc.state == 'cancel':
                raise exceptions.AccessError(_('You can not print QR Report for a Cancelled Manufacturing Order !'))
            for data in doc.finished_move_line_ids:
                if not data.lot_id:
                    raise exceptions.AccessError(_('You can not print QR Code as no Serial Number has been provided!'))
        return {
            'doc_ids': docs.ids,
            'doc_model': 'mrp.production',
            'docs': docs,
        }


class LotQRReportMOCurrent(models.AbstractModel):
    _name = "report.gts_so_mo_link.report_lot_qr_code_current"
    _description = 'report_lot_qr_code_current'

    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.lot'].browse(docids)
        for doc in docs:
            if doc.production_id.state == 'cancel':
                raise exceptions.AccessError(_('You can not download QR Report for a Cancelled Manufacturing Order !'))
        return {
            'data':data,
            'doc_ids': docs.ids,
            'doc_model': 'stock.lot',
            'docs': docs,
        }


class LotQRReportMOUpcoming(models.AbstractModel):
    _name = "report.gts_so_mo_link.report_lot_qr_code_upcoming"
    _description = 'report_lot_qr_code_upcoming'

    def _get_report_values(self, docids, data=None):
        docs = self.env['stock.lot'].browse(docids)
        for doc in docs:
            if doc.production_id.state == 'cancel':
                raise exceptions.AccessError(_('You can not download QR Report for a Cancelled Manufacturing Order !'))
        return {
            'data':data,
            'doc_ids': docs.ids,
            'doc_model': 'stock.lot',
            'docs': docs,
        }


class TestCertificateMOSingle(models.AbstractModel):
    _name = 'report.gts_so_mo_link.single_report_mrp_test_certificate'
    _description = 'single_report_mrp_test_certificate'

    def _get_report_values(self, docids, data=None):
        docs = self.env['test.report.mo'].browse(docids)
        for doc in docs:
            if not doc.production_id.finished_move_line_ids:
                raise exceptions.AccessError(_('You Cannot Download Test Certificate as there is no Quantity Produced !'))
            if doc.production_id.state == 'cancel':
                raise exceptions.AccessError(_('You can not download Test Report for a Cancelled Manufacturing Order !'))
        return {
            'doc_ids': docs.ids,
            'doc_model': 'test.report.mo',
            'docs': docs,
        }


class TestCertificateMOSingleWithoutHF(models.AbstractModel):
    _name = 'report.gts_so_mo_link.single_without_hf_test_certificate'
    _description = 'single_without_hf_test_certificate'


    def _get_report_values(self, docids, data=None):
        docs = self.env['test.report.mo'].browse(docids)
        for doc in docs:
            if not doc.production_id.finished_move_line_ids:
                raise exceptions.AccessError(_('You Cannot Download Test Certificate as there is no Quantity Produced !'))
            if doc.production_id.state == 'cancel':
                raise exceptions.AccessError(_('You can not download Test Report for a Cancelled Manufacturing Order !'))
        return {
            'doc_ids': docs.ids,
            'doc_model': 'test.report.mo',
            'docs': docs,
        }


# class StockRule(models.Model):
#     _inherit = "stock.rule"
#
#     def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values,
#                          bom):
#         val = super(StockRule, self)._prepare_mo_vals(product_id, product_qty, product_uom, location_id, name, origin,
#                                                       company_id, values, bom)
#         print(values)
#         if origin:
#             sale_order = self.env['sale.order'].search([('name', '=', origin)], limit=1)
#             if sale_order:
#                 val['partner_id'] = sale_order.partner_id.id
#                 val['client_order_ref'] = sale_order.client_order_ref
#                 val['delivery_date'] = sale_order.commitment_date
#         return val


class ProductionLot(models.Model):
    _inherit = 'stock.lot'

    name = fields.Char(
        'Lot/Serial Number', default=lambda self: self.env['ir.sequence'].next_by_code('stock.lot.serial'),
        required=True, help="Unique Lot/Serial Number", tracking=True)
    ref = fields.Char('Internal Reference', tracking=True,
                      help="Internal reference number in case it differs from the manufacturer's lot/serial number")
    product_id = fields.Many2one(
        'product.product', 'Product', index=True,
        domain=("[('tracking', '!=', 'none'), ('type', '=', 'product')] +"
                " ([('product_tmpl_id', '=', context['default_product_tmpl_id'])] if context.get('default_product_tmpl_id') else [])"),
        required=True, check_company=True,tracking=True)
    qr_code = fields.Binary("QR Code", attachment=True)
    attach_production_report = fields.Binary('Production Report', copy=False)
    attach_production_report_name = fields.Char('Production Report')
    pdf_attachment_id = fields.Many2one('ir.attachment')
    test_report = fields.Binary('Test Report', tracking=True)
    test_report_name = fields.Char('Test Report Name')
    used_lot = fields.Boolean('Used Lot')
    # battery_type = fields.Char('Battery Type', tracking=True)
    # rated_capacity = fields.Char('Rated Capacity', tracking=True)
    # rate_on_sample_cell = fields.Char('Rate Obtained on Sample Cell', tracking=True)
    production_id = fields.Many2one('mrp.production', string='MO')
    # invoice_date = fields.Date('Invoice Date')
    test_report_id = fields.Many2one('test.report.mo', 'Test Report')
    mo_date = fields.Date('MO Date')
    delivery_date = fields.Date('Delivery Date')
    product_type = fields.Selection(related='product_id.product_type', string='Item Type')
    product_qty = fields.Float('Quantity', compute='_product_qty')

    # @api.depends('quant_ids','quant_ids.quantity')
    # def _product_qty(self):
    #     for lot in self:
    #         # We only care for the quants in internal or transit locations.
    #         quants = lot.quant_ids.filtered(lambda q: q.location_id.usage == 'internal' or (
    #                     q.location_id.usage == 'transit' and q.location_id.company_id))
    #         lot.product_qty = sum(quants.mapped('quantity'))
    # warranty_mo_date = fields.Date('Warranty Date on MO', compute='_get_warranty_mo_date', store=True)
    # warranty_delivery_date = fields.Date('Warranty Date on Delivery', compute='_get_warranty_delivery_date', store=True)
    # start_date = fields.Date('Validity From')
    # end_date = fields.Date('Validity To')
    # invoice_number = fields.Char(string='Invoice No.')

    # @api.depends('mo_date')
    # def _get_warranty_mo_date(self):
    #     for data in self:
    #         data.warranty_mo_date = False
    #         if data.mo_date:
    #             if data.product_id.product_warranty > 0:
    #                 data.warranty_mo_date = data.mo_date + timedelta(
    #                     days=365 * int(data.product_id.product_warranty))
    #
    # @api.depends('delivery_date')
    # def _get_warranty_delivery_date(self):
    #     for data in self:
    #         data.warranty_delivery_date = False
    #         if data.delivery_date:
    #             if data.product_id.product_warranty > 0:
    #                 data.warranty_delivery_date = data.delivery_date + timedelta(
    #                     days=365 * int(data.product_id.product_warranty))


    # def create(self, vals_list):
    #     val = super(ProductionLot, self).create(vals_list)
    #     if val.product_id.tracking == 'serial':
    #         # content = "Eternity Industrial Batteries (India) LLP " + \
    #         #           "Building No. F8, Unit No. 9 & 10" + \
    #         #           "Pimplas, Bhiwandi 421302" + \
    #         #           "Email : info@eternitytechnologies.com" + \
    #         #           "Tel : 927 2222 380" + \
    #         #           "Toll Free : 1800 3132 648" + \
    #         #           "Capacity: " + str(val.product_id.ah) + \
    #         #           "Volts : " + str(val.product_id.volts) + " V" + \
    #         #           "No. of Cells :" + str((val.product_id.volts) / 2) + " Battery Serial No. :" + val.name
    #         content = "Eternity Industrial Batteries (India) LLP " + \
    #                   "Shiv Shanti Industrial & Logistics Park, " + \
    #                   "Bldg. No. A1/ Unit No. 2,3, & 4," + \
    #                   " Sonale Village, Bhiwandi-421302." + \
    #                   "Email : info@eternitytechnologies.com" + \
    #                   "Tel : 927 2222 380" + \
    #                   "Toll Free : 1800 3132 648" + \
    #                   "Capacity: " + str(val.product_id.ah) + \
    #                   "Volts : " + str(val.product_id.volts) + " V" + \
    #                   "No. of Cells :" + str((val.product_id.volts) / 2) + " Battery Serial No. :" + val.name
    #         qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4,)
    #         qr.add_data(content)
    #         qr.make(fit=True)
    #         img = qr.make_image()
    #         temp = BytesIO()
    #         img.save(temp, format="PNG")
    #         qr_image = base64.b64encode(temp.getvalue())
    #         val.qr_code = qr_image
    #     val.mo_date = date.today()
    #     active_id = self.env.context.get('active_id')
    #     if active_id:
    #         mrp = self.env['mrp.production'].search([('id', '=', active_id)], limit=1)
    #         if mrp:
    #             val.production_id = mrp.id
    #
    #             # stock_move = self.env['stock.move'].search([('raw_material_production_id', '=', mrp.id),
    #             #                                             ('product_id.product_type', '=', 'cell'),
    #             #                                             ('product_uom_qty', '>', 0)], limit=1)
    #             # volts = int(val.product_id.volts)
    #             # ah = int(val.product_id.ah)
    #             # qty, product_name = 0, ''
    #             # if stock_move:
    #             #     qty = int(stock_move.product_uom_qty / mrp.product_qty)
    #             #     product_name = stock_move.product_id.name
    #             # val.battery_type = str(volts) + " V " + str(ah) + " AH  (" + str(
    #             #     qty) + " x " + product_name + ")"
    #             # val.rated_capacity = str(ah) + " Ah"
    #             # val.rate_on_sample_cell = str(ah) + " Ah"
    #     # if val.production_id:
    #     #     if val.production_id.origin:
    #     #         invoice = self.env['account.move'].search(
    #     #             [('invoice_origin', '=', val.production_id.origin), ('state', '!=', 'cancel')], limit=1,
    #     #             order='create_date desc')
    #     #         if invoice:
    #     #             val.invoice_date = invoice.invoice_date
    #     return val

    def create(self, vals_list):
        val = super(ProductionLot, self).create(vals_list)

        if val.product_id.tracking == 'serial':
            content = (
                "Eternity Industrial Batteries (India) LLP\n"
                "Shiv Shanti Industrial & Logistics Park,\n"
                "Bldg. No. A1/ Unit No. 2,3, & 4,\n"
                "Sonale Village, Bhiwandi-421302.\n"
                "Email : info@eternitytechnologies.com\n"
                "Tel : 927 2222 380\n"
                "Toll Free : 1800 3132 648\n"
                f"Capacity: {val.product_id.ah}\n"
                f"Volts: {val.product_id.volts} V\n"
                f"No. of Cells: {int(val.product_id.volts / 2)}\n"
                f"Battery Serial No.: {val.name}"
            )

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(content)
            qr.make(fit=True)
            img = qr.make_image()
            temp = BytesIO()
            img.save(temp, format="PNG")
            qr_image = base64.b64encode(temp.getvalue())
            val.qr_code = qr_image

        val.mo_date = date.today()

        active_id = self.env.context.get('active_id')
        if active_id:
            mrp = self.env['mrp.production'].search([('id', '=', active_id)], limit=1)
            if mrp:
                val.production_id = mrp.id
        return val

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    attach_production_report = fields.Binary('Production Report', copy=False)
    attach_production_report_name = fields.Char('Attach Production Report')
    pdf_attachment_id = fields.Many2one('ir.attachment')


class StockMove(models.Model):
    _inherit = 'stock.move'

    attach_production_report = fields.Binary('Production Report', copy=False)
    attach_production_report_name = fields.Char('Attach Production Report')


# class MrpConsumptionWarningLine(models.TransientModel):
#     _inherit = 'mrp.consumption.warning.line'
#
#     product_id = fields.Many2one('product.product', "Product", required=True)

