from odoo import api, fields, models, tools, _
from datetime import datetime, date
import datetime
from datetime import timedelta
# import locale
# locale.setlocale(locale.LC_ALL, 'en_IN.utf8')
from babel.numbers import format_currency
from forex_python.converter import CurrencyRates
from odoo.http import request


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def scheduled_daily_analysis_report(self):
        # Cj: if the application is running on localhost or staging server do not sent mail.
        # current_url = str(request.env['ir.config_parameter'].get_param('web.base.url'))
        # if "staging" in current_url or "localhost" in current_url:
        #     return False
        dt = date.today()
        # Cj: if the application is running on localhost or staging server do not sent mail.
        # current_url = str(request.env['ir.config_parameter'].get_param('web.base.url'))
        # if "staging" in current_url or "localhost" in current_url:
            # return False


        today_ = dt.strftime('%Y-%m-%d')
        crm_obj = self.env['crm.lead']

        sale_obj = self.env['sale.order']
        sale_state_dict = {'draft': 'Quotation', 'sent': 'Quotation Sent', 'sale': 'Sales Order','done':'Locked','cancel':'Cancelled','sent_for_approval':'Sent For Approval','approved':'Approved'}

        purchase_obj = self.env['purchase.order']
        purchase_state_dict = {'draft':'RFQ','sent':'RFQ Sent','to approve':'To Approve','purchase':'Purchase Order','done':'Locked','cancel':'Cancelled'}

        account_move_obj = self.env['account.move']
        account_move_state_dict = {'draft':'Draft','posted':'Posted','cancel':'Cancelled'}

        payment_obj = self.env['account.payment']
        payment_state_dict ={'draft':'Draft','posted':'Posted','cancel':'Cancelled'}

        mrp_obj = self.env['mrp.production']
        mrp_state_dict = {'draft':'Draft','confirmed':'Confirmed','progress':'In Progress','to_close':'To Close','done':'Done','cancel':'Cancelled'}

        # CRM
        opp_created = crm_obj.search([('create_date', '>=', today_), ('create_date', '<=', today_),
                                      ('stage_id.name', '!=', 'Won')])
        crm_won = crm_obj.search([('type', '=', 'opportunity'), ('stage_id.name', '=', 'Won'),
                                  ('stage_id.is_won', '=', True), ('date_closed', '>=', today_),
                                  ('date_closed', '<=', today_)])
        crm_lost = crm_obj.search([('type', '=', 'opportunity'), ('date_closed', '>=', today_),
                                   ('date_closed', '<=', today_), ('active', '=', False)])

        # Sale
        quotation_prepared = sale_obj.search([('create_date', '>=', today_), ('create_date', '<=', today_),
                                              ('state', 'not in', ('sale', 'done', 'cancel'))])
        sale_orders = sale_obj.search([('date_order', '>=', today_), ('date_order', '<=', today_),
                                       ('state', '=', 'sale')])


        # Purchase
        purchase_rfq = purchase_obj.search([('state', 'in', ('draft', 'sent', 'to approve')),
                                            ('date_order', '<=', today_), ('date_order', '>=', today_)])
        purchase_po = purchase_obj.search([('state', '=', 'purchase'), ('date_approve', '<=', today_),
                                           ('date_approve', '>=', today_)])

        # Account
        inv_created = account_move_obj.search([('create_date', '>=', today_), ('create_date', '<=', today_),
                                               ('state', '!=', 'cancel'), ('payment_state', '!=', 'paid'),
                                               ('move_type', '=', 'out_invoice')])
        payment_created = payment_obj.search([('partner_type', '=', 'customer'), ('date', '>=', today_),
                                              ('date', '<=', today_)])
        bill_created = account_move_obj.search([('create_date', '>=', today_), ('create_date', '<=', today_),
                                                ('state', '!=', 'cancel'), ('payment_state', '!=', 'paid'),
                                                ('move_type', '=', 'in_invoice')])
        bill_payment_created = payment_obj.search([('partner_type', '=', 'supplier'), ('date', '>=', today_),
                                                   ('date', '<=', today_)])


        # MRP
        mrp_create = mrp_obj.search([('create_date', '>=', today_), ('create_date', '<=', today_),
                                     ('state', 'not in', ('done', 'cancel'))])
        mrp_done = mrp_obj.search([('state', '=', 'done'), ('date_finished', '>=', today_),
                                   ('date_finished', '<=', today_)])
        mrp_to_do = mrp_obj.search([('state', 'in', ('draft', 'confirmed','progress', 'to_close'))])

        template = self.env.ref('gts_daily_analysis_email_report.email_template_daily_analysis_report')
        users_list = self.env['res.users'].search([])
        mail = self.env['mail.mail']
        c = CurrencyRates()

        for group_user in users_list:
            if group_user.has_group('gts_daily_analysis_email_report.group_daily_analysis_report_access'):

                # -------------------------- Opportunity Created -------------------

                body_opp_create = """
                    <p>Hi Team,</p>
                    <p>Please find Today's Analysis below:</p><br/>
                    <p><b>Opportunity Created</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_opp_create += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Opportunity Name</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Expected Closing</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Salesperson</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Probability (%)</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Expected Revenue</b></td>
                    </tr>
                """
                total_revenue = 0
                for data in opp_created:
                    total_revenue += data.expected_revenue
                    deadline_date = ''
                    if data.date_deadline:
                        deadline_date = data.date_deadline.strftime('%d/%m/%Y')
                    body_opp_create += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{opp_name}</td>
                            <td align="center" style="border: 1px solid">{closing_date}</td>
                            <td align="center" style="border: 1px solid">{salesperson}</td>
                            <td align="right" style="border: 1px solid">{probability}</td>
                            <td align="right" style="border: 1px solid">{revenue}</td>
                        </tr>
                    """.format(partner=data.partner_id.parent_id.name if not data.partner_id.name and data.partner_id.parent_id else data.partner_id.name, opp_name=data.name, closing_date=deadline_date,
                               salesperson=data.user_id.name, probability=data.probability,
                               revenue=format_currency(data.expected_revenue, 'INR', locale='en_IN'))

                body_opp_create += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_revenue}</b></td>
                    </tr>
                """.format(total_revenue=format_currency(total_revenue, 'INR', locale='en_IN'))

                body_opp_create += """</tbody></table>"""

                # ------------------------- Opportunity Won ---------------------

                body_header_won = """
                    <br/><p><b>Opportunity Won</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_header_won += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Opportunity Name</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Expected Closing</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Salesperson</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Expected Revenue</b></td>
                    </tr>
                """
                total_revenue = 0
                for data in crm_won:
                    total_revenue += data.expected_revenue
                    close_date, deadline_date = '', ''
                    if data.date_closed:
                        close_date = data.date_closed.strftime('%d/%m/%Y')
                    if data.date_deadline:
                        deadline_date = data.date_deadline.strftime('%d/%m/%Y')
                    body_header_won += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{opp_name}</td>
                            <td align="center" style="border: 1px solid">{closing_date}</td>
                            <td align="center" style="border: 1px solid">{salesperson}</td>
                            <td align="right" style="border: 1px solid">{revenue}</td>
                        </tr>
                    """.format(
                        partner=data.partner_id.display_name, opp_name=data.name,
                        closing_date=deadline_date,
                        revenue=format_currency(data.expected_revenue, 'INR', locale='en_IN'),
                        salesperson=data.user_id.name
                    )

                body_header_won += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_revenue}</b></td>
                    </tr>
                """.format(total_revenue=format_currency(total_revenue, 'INR', locale='en_IN'))

                body_header_won += """</tbody></table>"""

                # ---------------------------- Opportunity Lost -----------------------------

                body_header_lost = """
                    <br/><p><b>Opportunity Lost</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_header_lost += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Opportunity Name</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Lost Reason</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Expected Closing</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Salesperson</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Expected Revenue</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Stage</b></td>
                    </tr>
                """
                total_revenue = 0
                for data in crm_lost:
                    total_revenue += data.expected_revenue
                    close_date, deadline_date = '', ''
                    if data.date_closed:
                        close_date = data.date_closed.strftime('%d/%m/%Y')
                    if data.date_deadline:
                        deadline_date = data.date_deadline.strftime('%d/%m/%Y')
                    body_header_lost += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{opp_name}</td>
                            <td align="center" style="border: 1px solid">{lost_reason}</td>
                            <td align="center" style="border: 1px solid">{closing_date}</td>
                            <td align="center" style="border: 1px solid">{salesperson}</td>
                            <td align="right" style="border: 1px solid">{revenue}</td>
                            <td align="right" style="border: 1px solid">{stage}</td>
                        </tr>
                    """.format(partner=data.partner_id.parent_id.name if not data.partner_id.name and data.partner_id.parent_id else data.partner_id.name, opp_name=data.name,
                               closing_date=deadline_date, lost_reason=data.lost_reason.name,
                               revenue=format_currency(data.expected_revenue, 'INR', locale='en_IN'),
                               salesperson=data.user_id.name, stage=data.stage_id.name)

                body_header_lost += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_revenue}</b></td>
                        <td style="border: 1px solid"></td>
                    </tr>
                """.format(total_revenue=format_currency(total_revenue, 'INR', locale='en_IN'))

                body_header_lost += """</tbody></table>"""

                # ----------------------------- Quotation Prepared -------------------------

                body_quo_prepare = """
                    <br/><p><b>Quotation Prepared</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_quo_prepare += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Quotation No.</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Salesperson</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total Cost</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Untaxed Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Tax Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Margin</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Margin (%)</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                total_amount, margin, avg_margin_percentage, total_sale_amount, total_cost_price, total_tax_amount, total_po_value = 0, 0, 0, 0, 0, 0, 0
                for data in quotation_prepared:
                    rate = c.get_rate(data.pricelist_id.currency_id.name, 'INR')

                    total_amount += data.amount_total * rate
                    margin += data.margin
                    total_sale_amount += data.amount_untaxed * rate
                    total_tax_amount += data.amount_tax
                    total_po_value += data.po_value * rate
                    total_cost_price += data.total_purchase_price
                    if total_sale_amount != 0.0:
                        avg_margin_percentage = (margin / total_sale_amount) * 100


                    body_quo_prepare += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{name}</td>
                            <td align="center" style="border: 1px solid">{salesperson}</td>
                            <td align="right" style="border: 1px solid">{total_cost_price}</td>
                            <td align="right" style="border: 1px solid">{total_sale_price}</td>
                            <td align="right" style="border: 1px solid">{tax_amount}</td>
                            <td align="right" style="border: 1px solid">{total_amount}</td>
                            <td align="right" style="border: 1px solid">{margin}</td>
                            <td align="right" style="border: 1px solid">{margin_percentage}</td>
                            <td align="center" style="border: 1px solid">{status}</td>
                        </tr>
                    """.format(partner=data.partner_id.parent_id.name if not data.partner_id.name and data.partner_id.parent_id else data.partner_id.name,
                               po_amount=format_currency(data.po_value * rate, 'INR', locale='en_IN'),
                               total_amount=format_currency(data.amount_total * rate, 'INR', locale='en_IN'),
                               name=data.name, margin_percentage="{:.2f}".format(data.margin_percentage),
                               salesperson=data.user_id.name,
                               status=sale_state_dict.get(data.state),
                               margin=format_currency(data.margin * rate, 'INR', locale='en_IN'),
                               total_sale_price=format_currency(data.amount_untaxed * rate, 'INR', locale='en_IN'),
                               total_cost_price=format_currency(data.total_purchase_price , 'INR', locale='en_IN'),
                               tax_amount=format_currency(data.amount_tax, 'INR', locale='en_IN'))

                body_quo_prepare += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_cost_price}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_sale_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_tax_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{margin}</b></td>
                        <td align="right" style="border: 1px solid"><b>{avg_margin_percentage}</b></td>
                        <td style="border: 1px solid"></td>
                    </tr>
                """.format(total_amount=format_currency(total_amount, 'INR', locale='en_IN'),
                           margin=format_currency(margin, 'INR', locale='en_IN'),
                           avg_margin_percentage="{:.2f}".format(avg_margin_percentage),
                           total_sale_amount=format_currency(total_sale_amount, 'INR', locale='en_IN'),
                           total_cost_price=format_currency(total_cost_price, 'INR', locale='en_IN'),
                           total_tax_amount=format_currency(total_tax_amount, 'INR', locale='en_IN'))

                body_quo_prepare += """</tbody></table>"""

                # --------------------------- Sale Order ---------------------------

                body_sale_order = """
                    <br/><p><b>Sales Order Confirmed</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_sale_order += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Sales Order No.</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Salesperson</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>PO Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total Cost</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Untaxed Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Tax Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Margin</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Margin (%)</b></td>
                    </tr>
                """
                sale_margin, sale_avg_margin_percentage = 0,0
                total_amount, total_sale_amount, total_tax_amount, total_po_value, total_cost_price = 0, 0, 0, 0, 0
                for data in sale_orders:
                    rate = c.get_rate(data.pricelist_id.currency_id.name, 'INR')

                    total_amount += data.amount_total * rate
                    sale_margin += data.margin
                    total_sale_amount += data.amount_untaxed * rate
                    total_tax_amount += data.amount_tax
                    total_po_value += data.po_value * rate
                    total_cost_price += data.total_purchase_price
                    if total_sale_amount != 0.0:
                        sale_avg_margin_percentage = (sale_margin / total_sale_amount) * 100


                    body_sale_order += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{name}</td>
                            <td align="center" style="border: 1px solid">{salesperson}</td>
                            <td align="right" style="border: 1px solid">{po_value}</td>
                            <td align="right" style="border: 1px solid">{total_cost_price}</td>
                            <td align="right" style="border: 1px solid">{total_sale_price}</td>
                            <td align="right" style="border: 1px solid">{total_tax_amount}</td>
                            <td align="right" style="border: 1px solid">{total_amount}</td>
                            <td align="right" style="border: 1px solid">{margin}</td>
                            <td align="right" style="border: 1px solid">{margin_percentage}</td>
                        </tr>
                    """.format(partner=data.partner_id.parent_id.name if not data.partner_id.name and data.partner_id.parent_id else data.partner_id.name,
                               total_amount=format_currency(data.amount_total * rate, 'INR', locale='en_IN'),
                               po_value=format_currency(data.po_value * rate, 'INR', locale='en_IN'),
                               salesperson=data.user_id.name,
                               name=data.name, margin_percentage="{:.2f}".format(data.margin_percentage),
                               margin=format_currency(data.margin, 'INR', locale='en_IN'),
                               total_sale_price=format_currency(data.amount_untaxed * rate, 'INR', locale='en_IN'),
                               total_cost_price=format_currency(data.total_purchase_price, 'INR', locale='en_IN'),
                               total_tax_amount=format_currency(data.amount_tax, 'INR', locale='en_IN'))

                body_sale_order += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_po_value}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_cost_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_sale_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_tax_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{margin}</b></td>
                        <td align="right" style="border: 1px solid"><b>{avg_margin_percentage}</b></td>
                    </tr>
                """.format(total_amount=format_currency(total_amount, 'INR', locale='en_IN'),
                           margin=format_currency(sale_margin, 'INR', locale='en_IN'),
                           avg_margin_percentage="{:.2f}".format(sale_avg_margin_percentage),
                           total_po_value=format_currency(total_po_value, 'INR', locale='en_IN'),
                           total_sale_amount=format_currency(total_sale_amount, 'INR', locale='en_IN'),
                           total_cost_amount=format_currency(total_cost_price, 'INR', locale='en_IN'),
                           total_tax_amount=format_currency(total_tax_amount, 'INR', locale='en_IN'))

                body_sale_order += """</tbody></table>"""

                # ------------------------------ Purchase Created -----------------------

                body_purchase_rfq = """
                    <br/><p><b>Purchase Order Created</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                    <tr style="border: 1px solid;background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Vendor</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Purchase Order No.</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Representative</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Untaxed Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Taxes</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                tax_totals, tax_tot, tax_total = 0.0, 0.0, 0.0
                for rec_po in purchase_rfq:
                    rate = c.get_rate(rec_po.currency_id.name, 'INR')
                    tax_totals += rec_po.amount_untaxed * rate
                    tax_tot += rec_po.amount_tax
                    tax_total += rec_po.amount_total * rate

                    body_purchase_rfq += """
                        <tr style="border: 1px solid">
                            <td align="center" style="border: 1px solid">{partner_id}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{user_id}</td>
                            <td style="text-align:right;border: 1px solid;">{amount_untaxed}</td>
                            <td style="text-align:right;border: 1px solid;">{amount_tax}</td>
                            <td style="text-align:right;border: 1px solid;">{amount_total}</td>
                            <td align="center" style="border: 1px solid;">{status}</td>
                        </tr>
                    """.format(partner_id=rec_po.partner_id.name, user_id=rec_po.user_id.name, ref=rec_po.name or '',
                               amount_untaxed=format_currency(rec_po.amount_untaxed * rate, 'INR', locale='en_IN'),
                               amount_tax=format_currency(rec_po.amount_tax, 'INR', locale='en_IN'),
                               amount_total=format_currency(rec_po.amount_total * rate, 'INR', locale='en_IN'),
                               status=purchase_state_dict.get(rec_po.state))

                body_purchase_rfq += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="text-align:right;border: 1px solid;"><b>{amount_untaxed}</b></td>
                        <td style="text-align:right;border: 1px solid;"><b>{amount_tax}</b></td>
                        <td style="text-align:right;border: 1px solid;"><b>{amount_total}</b></td>
                        <td style="border: 1px solid;"></td>
                    </tr>
                """.format(amount_untaxed=format_currency(tax_totals, 'INR', locale='en_IN'),
                           amount_tax=format_currency(tax_tot, 'INR', locale='en_IN'),
                           amount_total=format_currency(tax_total, 'INR', locale='en_IN'))

                body_purchase_rfq += """</tbody></table>"""

                # ---------------------------- Confirm Purchase order --------------------------

                body_purchase_confirm = """
                    <br/><p><b>Purchase Order Confirmed</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                    <tr style="border: 1px solid;background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Vendor</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Purchase Order No.</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Representative</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Untaxed Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Taxes</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total</b></td>
                    </tr>
                """
                tax_totals, tax_tot, tax_total = 0.0, 0.0, 0.0
                for rec in purchase_po:
                    rate = c.get_rate(rec.currency_id.name, 'INR')

                    tax_totals += rec.amount_untaxed * rate
                    tax_tot += rec.amount_tax
                    tax_total += rec.amount_total * rate


                    body_purchase_confirm += """
                        <tr style="border: 1px solid">
                            <td align="center" style="border: 1px solid">{partner_id}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{user_id}</td>
                            <td style="text-align:right;border: 1px solid;">{amount_untaxed}</td>
                            <td style="text-align:right;border: 1px solid;">{amount_tax}</td>
                            <td style="text-align:right;border: 1px solid;">{amount_total}</td>
                       </tr>
                    """.format(partner_id=rec.partner_id.name, user_id=rec.user_id.name, ref=rec.name or '',
                               amount_untaxed=format_currency(rec.amount_untaxed * rate, 'INR', locale='en_IN'),
                               amount_tax=format_currency(rec.amount_tax, 'INR', locale='en_IN'),
                               amount_total=format_currency(rec.amount_total * rate, 'INR', locale='en_IN'))

                body_purchase_confirm += """
                    <tr style="border: 1px solid">
                            <td style="border: 1px solid"></td>
                            <td style="border: 1px solid"></td>
                            <td style="border: 1px solid"></td>
                            <td style="text-align:right;border: 1px solid;"><b>{amount_untaxed}</b></td>
                            <td style="text-align:right;border: 1px solid;"><b>{amount_tax}</b></td>
                            <td style="text-align:right;border: 1px solid;"><b>{amount_total}</b></td>
                    </tr>
                """.format(amount_untaxed=format_currency(tax_totals, 'INR', locale='en_IN'),
                           amount_tax=format_currency(tax_tot, 'INR', locale='en_IN'),
                           amount_total=format_currency(tax_total, 'INR', locale='en_IN'))

                body_purchase_confirm += """</tbody></table>"""

                # -------------------------- Invoice Created -------------------

                body_inv_create = """
                    <br/><p><b>Invoice Created</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_inv_create += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Invoice No.</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>PO Reference</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Created By</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Sales Order No.</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total Cost</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Untaxed Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Tax Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Margin</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Margin (%)</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                total_untaxed_amount, total_tax_amount, inv_avg_margin_percentage, inv_margin, final_total_amount, total_cost = 0, 0, 0, 0,0,0
                for data in inv_created:
                    rate = c.get_rate(data.currency_id.name, 'INR')

                    total_untaxed_amount += data.amount_untaxed * rate
                    total_tax_amount += data.amount_tax
                    final_total_amount += data.amount_total * rate
                    total_cost += data.total_purchase_price
                    inv_margin += data.margin
                    if total_untaxed_amount != 0.0 :
                        inv_avg_margin_percentage = (inv_margin / total_untaxed_amount) * 100


                    body_inv_create += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{number}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{create_by}</td>
                            <td align="center" style="border: 1px solid">{origin}</td>
                            <td align="right" style="border: 1px solid">{total_cost}</td>
                            <td align="right" style="border: 1px solid">{untaxed_amount}</td>
                            <td align="right" style="border: 1px solid">{tax_amount}</td>
                            <td align="right" style="border: 1px solid">{total_amount}</td>
                            <td align="right" style="border: 1px solid">{margin}</td>
                            <td align="right" style="border: 1px solid">{margin_percentage}</td>
                            <td align="center" style="border: 1px solid">{status}</td>
                        </tr>
                    """.format(partner=data.partner_id.parent_id.name if not data.partner_id.name and data.partner_id.parent_id else data.partner_id.name, origin=data.invoice_origin or '',
                               create_by=data.create_uid.name, ref=data.ref or '', number=data.name or '',
                               total_cost=format_currency(data.total_purchase_price, 'INR', locale='en_IN'),
                               untaxed_amount=format_currency(data.amount_untaxed, 'INR', locale='en_IN'),
                               tax_amount=format_currency(data.amount_tax, 'INR', locale='en_IN'),
                               total_amount=format_currency(data.amount_total, 'INR', locale='en_IN'),
                               margin=format_currency(data.margin, 'INR', locale='en_IN'),
                               margin_percentage="{:.2f}".format(data.margin_percentage),
                               status=account_move_state_dict.get(data.state))

                body_inv_create += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_cost}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_untaxed_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_tax_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{final_total_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{margin}</b></td>
                        <td align="right" style="border: 1px solid"><b>{avg_margin_percentage}</b></td>
                        <td style="border: 1px solid"></td>
                    </tr>
                """.format(total_untaxed_amount=format_currency(total_untaxed_amount, 'INR', locale='en_IN'),
                           total_tax_amount=format_currency(total_tax_amount, 'INR', locale='en_IN'),
                           total_cost=format_currency(total_cost, 'INR', locale='en_IN'),
                           final_total_amount=format_currency(final_total_amount, 'INR', locale='en_IN'),
                           margin=format_currency(inv_margin, 'INR', locale='en_IN'),
                           avg_margin_percentage="{:.2f}".format(inv_avg_margin_percentage))

                body_inv_create += """</tbody></table>"""

                # ------------------------- Customer Payments ------------------------

                body_payment_create = """
                    <br/><p><b>Payments Received</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_payment_create += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Bank</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Reference</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Created By</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Payment Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                total_amount = 0
                for record in payment_created:
                    rate = c.get_rate(record.currency_id.name, 'INR')

                    total_amount += record.amount * rate
                    body_payment_create += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{payment_received}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{create_by}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                            <td align="center" style="border: 1px solid">{status}</td>
                        </tr>
                    """.format(partner=record.partner_id.parent_id.name if not record.partner_id.name and record.partner_id.parent_id else record.partner_id.name, payment_received=record.journal_id.name or '',
                               ref=record.payment_reference or '', create_by=record.create_uid.name,
                               number=record.name or '',
                               amount=format_currency(record.amount * rate, 'INR', locale='en_IN'),
                               status=payment_state_dict.get(record.state))
                               # status=dict(self._fields['state'].selection).get(record.state))

                body_payment_create += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_amount}</b></td>
                        <td style="border: 1px solid"></td>
                    </tr>
                """.format(total_amount=format_currency(total_amount, 'INR', locale='en_IN'))

                body_payment_create += """</tbody></table>"""

                # -------------------------- Vendor Bill -----------------------

                body_ven_bill = """
                    <br/><p><b>Bills Created</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_ven_bill += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Vendor</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Bill Reference</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Created By</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>ET PO No.</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Untaxed Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Tax Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Total Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                total_untaxed_amount, total_tax_amount, final_total_amount = 0, 0, 0
                for data in bill_created:

                    rate = c.get_rate(data.currency_id.name, 'INR')

                    total_untaxed_amount += data.amount_untaxed * rate
                    total_tax_amount += data.amount_tax
                    final_total_amount += data.amount_total * rate
                    body_ven_bill += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{create_by}</td>
                            <td align="center" style="border: 1px solid">{origin}</td>
                            <td align="right" style="border: 1px solid">{untaxed_amount}</td>
                            <td align="right" style="border: 1px solid">{tax_amount}</td>
                            <td align="right" style="border: 1px solid">{total_amount}</td>
                            <td align="center" style="border: 1px solid">{status}</td>
                        </tr>
                    """.format(partner=data.partner_id.parent_id.name if not data.partner_id.name and data.partner_id.parent_id else data.partner_id.name, origin=data.invoice_origin or '',
                               create_by=data.create_uid.name, ref=data.ref or '', number=data.name or '',
                               untaxed_amount=format_currency(data.amount_untaxed * rate, 'INR', locale='en_IN'),
                               tax_amount=format_currency(data.amount_tax, 'INR', locale='en_IN'),
                               total_amount=format_currency(data.amount_total * rate, 'INR', locale='en_IN'),
                               status=account_move_state_dict.get(data.state))

                body_ven_bill += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_untaxed_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{total_tax_amount}</b></td>
                        <td align="right" style="border: 1px solid"><b>{final_total_amount}</b></td>
                        <td style="border: 1px solid"></td>
                    </tr>
                """.format(total_untaxed_amount=format_currency(total_untaxed_amount, 'INR', locale='en_IN'),
                           total_tax_amount=format_currency(total_tax_amount, 'INR', locale='en_IN'),
                           final_total_amount=format_currency(final_total_amount, 'INR', locale='en_IN'))

                body_ven_bill += """</tbody></table>"""

                # ---------------------------- Vendor Payments ----------------------

                body_ven_payment = """
                    <br/><p><b>Payments Made</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """
                body_ven_payment += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Vendor</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Bank</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Reference</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Created By</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Payment Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                total_amount = 0
                for record in bill_payment_created:
                    rate = c.get_rate(record.currency_id.name, 'INR')

                    total_amount += record.amount * rate
                    body_ven_payment += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{payment_received}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{create_by}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                            <td align="center" style="border: 1px solid">{status}</td>
                        </tr>
                    """.format(partner=record.partner_id.parent_id.name if not record.partner_id.name and record.partner_id.parent_id else record.partner_id.name, payment_received=record.journal_id.name or '',
                               ref=record.payment_reference or '', create_by=record.create_uid.name,
                               number=record.name or '',
                               amount=format_currency(record.amount * rate, 'INR', locale='en_IN'),
                               status=payment_state_dict.get(record.state))

                body_ven_payment += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{total_amount}</b></td>
                        <td style="border: 1px solid"></td>
                    </tr>
                """.format(total_amount=format_currency(total_amount, 'INR', locale='en_IN'))

                body_ven_payment += """</tbody></table>"""

                # ----------------------------- MRP Create ---------------------

                body_mrp_create = """
                    <br/><p><b>Manufacturing Order Created</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """

                body_mrp_create += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Reference</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Planned Date</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Delivery Date</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Source</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Product</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Quantity</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Responsible</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                total_quantity = 0
                for mrp in mrp_create:
                    total_quantity += mrp.product_qty
                    planned_date, delivery_date = '', ''
                    if mrp.date_start:
                        planned_date = mrp.date_start.strftime('%d/%m/%Y')
                    if mrp.delivery_date:
                        delivery_date = mrp.delivery_date.strftime('%d/%m/%Y')
                    body_mrp_create += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{planned_date}</td>
                            <td align="center" style="border: 1px solid">{delivery_date}</td>
                            <td align="center" style="border: 1px solid">{source}</td>
                            <td align="center" style="border: 1px solid">{product}</td>
                            <td align="center" style="border: 1px solid">{quantity}</td>
                            <td align="center" style="border: 1px solid">{responsible}</td>
                            <td align="center" style="border: 1px solid">{status}</td>
                        </tr>
                    """.format(partner=mrp.partner_id.parent_id.name if not mrp.partner_id.name and mrp.partner_id.parent_id else mrp.partner_id.name, ref=mrp.name or '', planned_date=planned_date,
                               delivery_date=delivery_date, source=mrp.origin or '', product=mrp.product_id.name or '',
                               responsible=mrp.user_id.name or '',
                               quantity=int(mrp.product_qty),
                               status=mrp_state_dict.get(mrp.state))

                body_mrp_create += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid"></td>
                            <td align="center" style="border: 1px solid"></td>
                            <td align="center" style="border: 1px solid"></td>
                            <td align="center" style="border: 1px solid"></td>
                            <td align="center" style="border: 1px solid"></td>
                            <td align="center" style="border: 1px solid"></td>
                            <td align="center" style="border: 1px solid"><b>{total_quantity}</b></td>
                            <td align="center" style="border: 1px solid"></td>
                            <td align="center" style="border: 1px solid"></td>
                        </tr>
                    """.format(total_quantity=int(total_quantity))

                body_mrp_create += """</tbody></table>"""

                # ------------------------ MRP confirm ---------------------

                body_mrp_confirm = """
                    <br/><p><b>Manufacturing Order Completed</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """

                body_mrp_confirm += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Reference</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Planned Date</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Delivery Date</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Source</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Product</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Quantity</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Responsible</b></td>
                    </tr>
                """
                total_quantity = 0
                for mrp in mrp_done:
                    total_quantity += mrp.product_qty
                    planned_date, delivery_date = '', ''
                    if mrp.date_start:
                        planned_date = mrp.date_start.strftime('%d/%m/%Y')
                    if mrp.delivery_date:
                        delivery_date = mrp.delivery_date.strftime('%d/%m/%Y')
                    body_mrp_confirm += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{planned_date}</td>
                            <td align="center" style="border: 1px solid">{delivery_date}</td>
                            <td align="center" style="border: 1px solid">{source}</td>
                            <td align="center" style="border: 1px solid">{product}</td>
                            <td align="center" style="border: 1px solid">{quantity}</td>
                            <td align="center" style="border: 1px solid">{responsible}</td>
                        </tr>
                    """.format(partner=mrp.partner_id.parent_id.name if not mrp.partner_id.name and mrp.partner_id.parent_id else mrp.partner_id.name, ref=mrp.name or '', planned_date=planned_date,
                               delivery_date=delivery_date, source=mrp.origin or '', product=mrp.product_id.name or '',
                               responsible=mrp.user_id.name or '', quantity=int(mrp.product_qty))
                body_mrp_confirm += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"><b>{total_quantity}</b></td>
                        <td align="center" style="border: 1px solid"></td>
                    </tr>
                """.format(total_quantity=int(total_quantity))

                body_mrp_confirm += """</tbody></table>"""

                # ------------------------ MRP To Do ---------------------

                body_mrp_to_do = """
                    <br/><p><b>Manufacturing Order Pending</b></p><br/>
                    <table cellpadding=4 style="width: 100%; border: 3px solid;border-collapse:collapse">
                    <tbody>
                """

                body_mrp_to_do += """
                    <tr style="border: 1px solid; background-color:#2f756f;">
                        <td align="center" style="border: 1px solid;color:white;"><b>Customer</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Reference</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Planned Date</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Delivery Date</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Source</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Product</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Quantity</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Responsible</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Untaxed Amount</b></td>
                        <td align="center" style="border: 1px solid;color:white;"><b>Status</b></td>
                    </tr>
                """
                total_quantity, tot_untaxed_amount, untaxed_amount = 0, 0, 0
                for mrp in mrp_to_do:
                    # rate = c.get_rate(mrp.currency_id.name, 'INR')

                    if mrp.untaxed_amount_updated and mrp.untaxed_amount > 0.0:
                        untaxed_amount = mrp.untaxed_amount
                    tot_untaxed_amount +=mrp.untaxed_amount
                    total_quantity += mrp.product_qty
                    planned_date, delivery_date = '', ''
                    # state =
                    if mrp.date_start:
                        planned_date = mrp.date_start.strftime('%d/%m/%Y')
                    if mrp.delivery_date:
                        delivery_date = mrp.delivery_date.strftime('%d/%m/%Y')
                    body_mrp_to_do += """
                        <tr style="border: 1px solid">
                            <td style="border: 1px solid">{partner}</td>
                            <td align="center" style="border: 1px solid">{ref}</td>
                            <td align="center" style="border: 1px solid">{planned_date}</td>
                            <td align="center" style="border: 1px solid">{delivery_date}</td>
                            <td align="center" style="border: 1px solid">{source}</td>
                            <td align="center" style="border: 1px solid">{product}</td>
                            <td align="center" style="border: 1px solid">{quantity}</td>
                            <td align="center" style="border: 1px solid">{responsible}</td>
                            <td align="right" style="border: 1px solid">{untaxed_amount}</td>
                            <td align="center" style="border: 1px solid">{status}</td>
                        </tr>
                    """.format(partner=mrp.partner_id.parent_id.name if not mrp.partner_id.name and mrp.partner_id.parent_id else mrp.partner_id.name, ref=mrp.name or '', planned_date=planned_date,
                               delivery_date=delivery_date, source=mrp.origin or '', product=mrp.product_id.name or '',
                               responsible=mrp.user_id.name or '', quantity=int(mrp.product_qty),
                               status=mrp_state_dict.get(mrp.state),
                               untaxed_amount=format_currency(mrp.untaxed_amount, 'INR', locale='en_IN'))
                body_mrp_to_do += """
                    <tr style="border: 1px solid">
                        <td style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="center" style="border: 1px solid"><b>{total_quantity}</b></td>
                        <td align="center" style="border: 1px solid"></td>
                        <td align="right" style="border: 1px solid"><b>{untaxed_amount}</b></td>
                        <td align="center" style="border: 1px solid"></td>
                    </tr>
                """.format(total_quantity=int(total_quantity),
                           untaxed_amount=format_currency(tot_untaxed_amount, 'INR', locale='en_IN'))

                body_mrp_to_do += """</tbody></table>"""

                # ------------------------ Template -------------------------

                if template:
                    template.email_from ="odoo@eternitytechnologies.com"
                    template.email_to = group_user.login
                    template['email_cc'] = 'milind.deshpande@eternitytechnologies.com'
                    template['body_html'] = body_opp_create + body_header_won + body_header_lost + body_quo_prepare \
                                            + body_sale_order + body_purchase_rfq + body_purchase_confirm + \
                                            body_inv_create + body_payment_create + body_ven_bill + body_ven_payment + \
                                            body_mrp_create + body_mrp_confirm + body_mrp_to_do

                    # email_vals = {
                    #     'email_from':"admin@eternitytechnologies.com",
                    #     'email_to': group_user.login,
                    #     'body_html' : body_opp_create + body_header_won + body_header_lost + body_quo_prepare \
                    #                         + body_sale_order + body_purchase_rfq + body_purchase_confirm + \
                    #                         body_inv_create + body_payment_create + body_ven_bill + body_ven_payment + \
                    #                         body_mrp_create + body_mrp_confirm + body_mrp_to_do
                    # }
                    template.send_mail(group_user.id,force_send=True)
                    # mail.create(email_vals).send()
                    # template.send_mail(self.id)
