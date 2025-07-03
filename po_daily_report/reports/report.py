import operator
from odoo import fields, api, models
import datetime
from itertools import chain
from dateutil.relativedelta import relativedelta
from babel.numbers import format_currency
import base64
from datetime import datetime

today = datetime.now().date()
from_year = today.year - 1 if today.month < 4 else today.year
to_year = today.year + 1 if today.month > 3 else today.year
from_date = datetime.strptime("01/04/" + str(from_year), "%d/%m/%Y").date()
to_date = datetime.strptime("31/03/" + str(to_year), "%d/%m/%Y").date()


class AccountInheritPO(models.Model):
    _inherit = 'account.move'

    def get_top_customer(self):
        result = self.sudo().read_group(
            [('state', '=', 'posted'), ('move_type', '=', 'out_invoice'), ('partner_id', '!=', False),
             ('invoice_date', '>=', from_date)
                , ('invoice_date', '<=', to_date)],
            fields=['partner_id.name', 'amount_total:sum(amount_total)'],
            groupby=['partner_id'], orderby="amount_total DESC", limit=5)
        data = []
        for rec in result:
            data.append({'partner_name': rec['partner_id'][1], 'amount_total': round(rec['amount_total'], 2)})

        return data

    def get_top_supplier(self):
        result = self.sudo().read_group(
            [('state', '=', 'posted'), ('move_type', '=', 'in_invoice'), ('partner_id', '!=', False),
             ('invoice_date', '>=', from_date), ('invoice_date', '<=', to_date), ('service_bill', '=', False)],
            fields=['partner_id.name', 'amount_total:sum(amount_total)'],
            groupby=['partner_id'], orderby="amount_total DESC", limit=5)
        data = []
        for rec in result:
            data.append({'partner_name': rec['partner_id'][1], 'amount_total': round(rec['amount_total'], 2)})
        return data

    #############################################################################

    def top_os_customer(self):
        result = self.sudo().read_group(
            [('state', '=', 'posted'), ('move_type', '=', 'out_invoice'), ('partner_id', '!=', False),
             ('amount_residual', '>', 0),
             ('invoice_date', '>=', from_date), ('invoice_date', '<=', to_date)],
            fields=['partner_id.name', 'total_amount_residual:sum(amount_residual)'],
            groupby=['partner_id'], orderby="total_amount_residual DESC", limit=5)
        data = []
        for rec in result:
            data.append(
                {'partner_name': rec['partner_id'][1], 'total_amount_residual': round(rec['total_amount_residual'], 2)})
        return data

    def top_os_supplier(self):
        result = self.sudo().read_group(
            [('state', '=', 'posted'), ('move_type', '=', 'in_invoice'), ('partner_id', '!=', False),
             ('amount_residual', '>', 0),
             ('invoice_date', '>=', from_date), ('invoice_date', '<=', to_date), ('service_bill', '=', False)],
            fields=['partner_id.name', 'total_amount_residual:sum(amount_residual)'],
            groupby=['partner_id'], orderby="total_amount_residual DESC", limit=5)
        data = []
        for rec in result:
            data.append(
                {'partner_name': rec['partner_id'][1], 'total_amount_residual': round(rec['total_amount_residual'], 2)})
        return data

    def top_over_due_customer(self):
        result = self.sudo().read_group(
            [('state', '=', 'posted'), ('move_type', '=', 'out_invoice'), ('partner_id', '!=', False),
             ('amount_residual', '>', 0),
             ('invoice_date_due', '<', today), ('invoice_date', '>=', from_date), ('invoice_date', '<=', to_date)],
            fields=['partner_id.name', 'total_amount_residual:sum(amount_residual)', 'invoice_date_due'],
            groupby=['partner_id'], orderby="total_amount_residual DESC", limit=5)
        data = []
        for rec in result:
            data.append(
                {'partner_name': rec['partner_id'][1], 'total_amount_residual': round(rec['total_amount_residual'], 2)})
        return data

    def top_over_due_supplier(self):
        result = self.sudo().read_group(
            [('state', '=', 'posted'), ('move_type', '=', 'in_invoice'), ('partner_id', '!=', False),
             ('amount_residual', '>', 0),
             ('invoice_date_due', '<', today), ('invoice_date', '>=', from_date), ('invoice_date', '<=', to_date),
             ('service_bill', '=', False)],
            fields=['partner_id.name', 'total_amount_residual:sum(amount_residual)'],
            groupby=['partner_id'], orderby="total_amount_residual DESC", limit=5)
        data = []
        for rec in result:
            data.append(
                {'partner_name': rec['partner_id'][1], 'total_amount_residual': round(rec['total_amount_residual'], 2)})
        return data

    def get_sales_purchases(self):
        sales = self.sudo().read_group(
            [('state', '=', 'posted'), ('invoice_date', '>=', from_date), ('invoice_date', '<=', to_date),
             ('journal_id.type', '=', 'sale')], fields=['total_amount:sum(amount_total)'],
            groupby=[])
        purchase = self.sudo().read_group(
            [('state', '=', 'posted'), ('invoice_date', '>=', from_date), ('invoice_date', '<=', to_date),
             ('journal_id.type', '=', 'purchase')],
            fields=['total_amount:sum(amount_total)'], groupby=[])
        return {'sales': sales[0]['total_amount'], 'purchase': purchase[0]['total_amount']}


class AccountMoveLineInherit(models.Model):
    _inherit = 'account.move.line'

    # def get_cash_flow(self):
    #     query = '''
    #         SELECT ARRAY_AGG(DISTINCT default_account_id),
    #                ARRAY_AGG(DISTINCT payment_debit_account_id),
    #                ARRAY_AGG(DISTINCT payment_credit_account_id)
    #         FROM account_journal
    #         WHERE type in ('cash','bank') and active = 't';
    #     '''
    #     self._cr.execute(query)
    #     res = self._cr.fetchall()[0]
    #     accounts = set((res[0] or []) + (res[1] or []) + (res[2] or []))
    #     accounts = list(accounts)
    #     result = self.sudo().read_group([('move_id.state', '=', 'posted'), ('account_id', 'in', accounts)],
    #                                     fields=['total_debit:sum(debit)', 'total_credit:sum(credit)'], groupby=[])
    #     return result

    def get_cash_bank_balance(self):
        result = self.sudo().read_group(
            [('move_id.state', '=', 'posted'), ('account_id.account_type', '=', 'asset_cash')],
            fields=['account_id.name', 'total_debit:sum(debit)', 'total_credit:sum(credit)'],
            groupby=['account_id'])
        data = []
        for rec in result:
            data.append(
                {'account_name': rec['account_id'][1], 'balance': round((rec['total_debit'] - rec['total_credit']), 2)})
        return data

    def get_top_sold_battery_vol(self):

        result = self.sudo().read_group(
            [('move_id.state', '=', 'posted'), ('move_id.move_type', '=', 'out_invoice'), ('product_id', '!=', False),
             ('product_id.product_type', '=', 'battery'), ('move_id.invoice_date', '>=', from_date)
                , ('move_id.invoice_date', '<=', to_date)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(price_subtotal)', 'move_id'],
            groupby=['product_id'], orderby="total_quantity DESC", limit=5)
        data = []
        for rec in result:
            product = self.env['product.product'].sudo().search([('id', '=', rec['product_id'][0])])
            data.append({'product': product, 'total_quantity': rec['total_quantity'],
                         'total_price': round(rec['total_price'], 2)})
        return data

    # def get_top_sold_cell_vol(self):
    #     result = self.sudo().read_group([('move_id.state','=','posted'),('move_id.move_type','=','out_invoice'),('product_id','!=',False),
    #                                      ('product_id.product_type','=','cell'),('move_id.invoice_date','>=',from_date)
    #                                         ,('move_id.invoice_date','<=',to_date)],fields=['product_id.name','total_quantity:sum(quantity)','total_price:sum(price_subtotal)','move_id'],
    #                                     groupby=['product_id'], orderby="total_quantity DESC",limit=5)
    #     data = []
    #     for rec in result:
    #         data.append({'product_name':rec['product_id'][1],'total_quantity':rec['total_quantity'],'total_price':round(rec['total_price'],2)})
    #     return data

    def get_top_sold_battery_val(self):
        result = self.sudo().read_group(
            [('move_id.state', '=', 'posted'), ('move_id.move_type', '=', 'out_invoice'), ('product_id', '!=', False),
             ('product_id.product_type', '=', 'battery'), ('move_id.invoice_date', '>=', from_date)
                , ('move_id.invoice_date', '<=', to_date)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(price_subtotal)', 'move_id'],
            groupby=['product_id'], orderby="total_price DESC", limit=5)
        data = []
        for rec in result:
            product = self.env['product.product'].sudo().search([('id', '=', rec['product_id'][0])])
            data.append({'product': product, 'total_quantity': rec['total_quantity'],
                         'total_price': round(rec['total_price'], 2)})
        return data

    # def get_top_sold_cell_val(self):
    #     result = self.sudo().read_group([('move_id.state','=','posted'),('move_id.move_type','=','out_invoice'),('product_id','!=',False),
    #                                      ('product_id.product_type','=','cell'),('move_id.invoice_date','>=',from_date)
    #                                         ,('move_id.invoice_date','<=',to_date)],fields=['product_id.name','total_quantity:sum(quantity)','total_price:sum(price_subtotal)','move_id'],
    #                                     groupby=['product_id'], orderby="total_price DESC",limit=5)
    #     data = []
    #     for rec in result:
    #         data.append({'product_name':rec['product_id'][1],'total_quantity':rec['total_quantity'],'total_price':round(rec['total_price'],2)})
    #     return data

    def get_top_purchased_battery_vol(self):
        result = self.sudo().read_group(
            [('move_id.state', '=', 'posted'), ('move_id.move_type', '=', 'in_invoice'), ('product_id', '!=', False),
             ('product_id.product_type', '=', 'battery'), ('move_id.invoice_date', '>=', from_date),
             ('move_id.invoice_date', '<=', to_date)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(price_subtotal)', 'move_id'],
            groupby=['product_id'], orderby="total_quantity DESC", limit=5)
        data = []
        for rec in result:
            product = self.env['product.product'].sudo().search([('id', '=', rec['product_id'][0])])
            data.append({'product': product, 'total_quantity': rec['total_quantity'],
                         'total_price': round(rec['total_price'], 2)})
        return data

    def get_top_purchased_cell_vol(self):
        result = self.sudo().read_group(
            [('move_id.state', '=', 'posted'), ('move_id.move_type', '=', 'in_invoice'), ('product_id', '!=', False),
             ('product_id.product_type', '=', 'cell'), ('move_id.invoice_date', '>=', from_date),
             ('move_id.invoice_date', '<=', to_date)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(price_subtotal)', 'move_id'],
            groupby=['product_id'], orderby="total_quantity DESC", limit=5)
        data = []
        for rec in result:
            data.append({'product_name': rec['product_id'][1], 'total_quantity': rec['total_quantity'],
                         'total_price': round(rec['total_price'], 2)})
        return data

    def get_top_purchased_battery_val(self):
        result = self.sudo().read_group(
            [('move_id.state', '=', 'posted'), ('move_id.move_type', '=', 'in_invoice'), ('product_id', '!=', False),
             ('product_id.product_type', '=', 'battery'), ('move_id.invoice_date', '>=', from_date),
             ('move_id.invoice_date', '<=', to_date)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(price_subtotal)', 'move_id'],
            groupby=['product_id'], orderby="total_price DESC", limit=5)
        data = []
        for rec in result:
            product = self.env['product.product'].sudo().search([('id', '=', rec['product_id'][0])])
            data.append({'product': product, 'total_quantity': rec['total_quantity'],
                         'total_price': round(rec['total_price'], 2)})
        return data

    def get_top_purchased_cell_val(self):
        result = self.sudo().read_group(
            [('move_id.state', '=', 'posted'), ('move_id.move_type', '=', 'in_invoice'), ('product_id', '!=', False),
             ('product_id.product_type', '=', 'cell'), ('move_id.invoice_date', '>=', from_date),
             ('move_id.invoice_date', '<=', to_date)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(price_subtotal)', 'move_id'],
            groupby=['product_id'], orderby="total_price DESC", limit=5)
        data = []
        for rec in result:
            data.append({'product_name': rec['product_id'][1], 'total_quantity': rec['total_quantity'],
                         'total_price': round(rec['total_price'], 2)})
        return data


class AccountJournalInherit(models.Model):
    _inherit = "account.journal"

    def get_bank_data(self):
        journal_id = self.search([('type', '=', 'bank')])
        data = list()
        for jrnl in journal_id:
            # move_line = self.env['account.move.line'].search([('account_id', '=', jrnl.default_account_id.id),('move_id.invoice_date','>=',from_date),('move_id.invoice_date','<=',to_date)])
            move_line = self.env['account.move.line'].search([('account_id', '=', jrnl.default_account_id.id)])
            debit = sum(move_line.mapped('debit'))
            credit = sum(move_line.mapped('credit'))
            total = debit - credit
            data.append((jrnl.name, round(total, 2)))
        return data

    @staticmethod
    def _get_move_line_fields(aml_alias="account_move_line"):
        return ', '.join('%s.%s' % (aml_alias, field) for field in (
            'id',
            'move_id',
            'name',
            'account_id',
            'journal_id',
            'company_id',
            'currency_id',
            'analytic_account_id',
            'display_type',
            'date',
            'debit',
            'credit',
            'balance',
        ))

    @api.model
    def _get_query_period_table(self, options):
        ''' Compute the periods to handle in the report.
        E.g. Suppose date = '2019-01-09', the computed periods will be:

        Name                | Start         | Stop
        --------------------------------------------
        As of 2019-01-09    | 2019-01-09    |
        1 - 30              | 2018-12-10    | 2019-01-08
        31 - 60             | 2018-11-10    | 2018-12-09
        61 - 90             | 2018-10-11    | 2018-11-09
        91 - 120            | 2018-09-11    | 2018-10-10
        Older               |               | 2018-09-10

        Then, return the values as an sql floating table to use it directly in queries.

        :return: A floating sql query representing the report's periods.
        '''

        def minus_days(date_obj, days):
            return fields.Date.to_string(date_obj - relativedelta(days=days))

        # date_str = options['date']['date_to']
        date_str = datetime.now().date()
        date = fields.Date.from_string(date_str)
        period_values = [
            (False, date_str),
            (minus_days(date, 1), minus_days(date, 30)),
            (minus_days(date, 31), minus_days(date, 60)),
            (minus_days(date, 61), minus_days(date, 90)),
            (minus_days(date, 91), minus_days(date, 120)),
            (minus_days(date, 121), False),
        ]

        period_table = ('(VALUES %s) AS period_table(date_start, date_stop, period_index)' %
                        ','.join("(%s, %s, %s)" for i, period in enumerate(period_values)))
        params = list(chain.from_iterable(
            (period[0] or None, period[1] or None, i)
            for i, period in enumerate(period_values)
        ))
        return self.env.cr.mogrify(period_table, params).decode(self.env.cr.connection.encoding)

    def get_age_receivable(self):
        date_to = datetime.now().date()
        # options = {'unfolded_lines': [],
        #            'date': {'string': 'As of 18/05/2022', 'period_type': 'today', 'mode': 'single', 'strict_range': False,
        #                     'date_from': '2022-05-01', 'date_to': date_to, 'filter': 'today'},
        #                     'partner': True, 'partner_ids': [], 'partner_categories': [], 'selected_partner_ids': [],
        #            'selected_partner_categories': [], 'unfold_all': False, 'selected_column': 0,
        #            'filter_account_type': 'receivable'}
        options = self.env['account.aged.receivable'].sudo()._get_options(previous_options=None)
        query = ("""
                       SELECT
                           {move_line_fields},
                           account_move_line.partner_id AS partner_id,
                           partner.name AS partner_name,
                           COALESCE(trust_property.value_text, 'normal') AS partner_trust,
                           COALESCE(account_move_line.currency_id, journal.currency_id) AS report_currency_id,
                           account_move_line.payment_id AS payment_id,
                           COALESCE(account_move_line.date_maturity, account_move_line.date) AS report_date,
                           account_move_line.expected_pay_date AS expected_pay_date,
                           move.move_type AS move_type,
                           move.name AS move_name,
                           journal.code AS journal_code,
                           account.name AS account_name,
                           account.code AS account_code,""" + ','.join([("""
                           CASE WHEN period_table.period_index = {i}
                           THEN %(sign)s * ROUND((
                               account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0)
                           ) * currency_table.rate, currency_table.precision)
                           ELSE 0 END AS period{i}""").format(i=i) for i in range(6)]) + """
                       FROM account_move_line
                       JOIN account_move move ON account_move_line.move_id = move.id
                       JOIN account_journal journal ON journal.id = account_move_line.journal_id
                       JOIN account_account account ON account.id = account_move_line.account_id
                       JOIN res_partner partner ON partner.id = account_move_line.partner_id
                       LEFT JOIN ir_property trust_property ON (
                           trust_property.res_id = 'res.partner,'|| account_move_line.partner_id
                           AND trust_property.name = 'trust'
                           AND trust_property.company_id = account_move_line.company_id
                       )
                       JOIN {currency_table} ON currency_table.company_id = account_move_line.company_id
                       LEFT JOIN LATERAL (
                           SELECT part.amount, part.debit_move_id
                           FROM account_partial_reconcile part
                           WHERE part.max_date <= %(date)s
                       ) part_debit ON part_debit.debit_move_id = account_move_line.id
                       LEFT JOIN LATERAL (
                           SELECT part.amount, part.credit_move_id
                           FROM account_partial_reconcile part
                           WHERE part.max_date <= %(date)s
                       ) part_credit ON part_credit.credit_move_id = account_move_line.id
                       JOIN {period_table} ON (
                           period_table.date_start IS NULL
                           OR COALESCE(account_move_line.date_maturity, account_move_line.date) <= DATE(period_table.date_start)
                       )
                       AND (
                           period_table.date_stop IS NULL
                           OR COALESCE(account_move_line.date_maturity, account_move_line.date) >= DATE(period_table.date_stop)
                       )
                       WHERE account.internal_type = %(account_type)s and move.state = 'posted'
                       GROUP BY account_move_line.id, partner.id, trust_property.id, journal.id, move.id, account.id,
                                period_table.period_index, currency_table.rate, currency_table.precision
                       HAVING ROUND(account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0), currency_table.precision) != 0
                   """).format(
            move_line_fields=self._get_move_line_fields('account_move_line'),
            currency_table=self.env['res.currency']._get_query_currency_table(options),
            period_table=self.env['account.aged.partner'].sudo()._get_query_period_table(options),
        )
        params = {
            'account_type': options['filter_account_type'],
            'sign': 1 if options['filter_account_type'] == 'receivable' else -1,
            'date': date_to,
        }
        query = self.env.cr.mogrify(query, params).decode(self.env.cr.connection.encoding)
        # query = self.env['account.aged.receivable'].sudo()._get_sql()
        data = self.env.cr.execute(query)
        data = self.env.cr.fetchall()
        receivable_data = {'as_on': 0, 'p1': 0, 'p2': 0, 'p3': 0, 'p4': 0, 'older': 0}
        for rec in data:
            # move = self.env['account.move'].sudo().search([('id', '=', rec[1]),('state','=','posted'),('invoice_date','>=',from_date)
            #                                                   ,('invoice_date','<=',to_date)])
            # if move:
            receivable_data['as_on'] = round((receivable_data['as_on'] + rec[-6]), 2)
            receivable_data['p1'] = round((receivable_data['p1'] + rec[-5]), 2)
            receivable_data['p2'] = round((receivable_data['p2'] + rec[-4]), 2)
            receivable_data['p3'] = round((receivable_data['p3'] + rec[-3]), 2)
            receivable_data['p4'] = round((receivable_data['p4'] + rec[-2]), 2)
            receivable_data['older'] = round((receivable_data['older'] + rec[-1]), 2)
        return receivable_data

    def get_age_payable(self):
        date_to = datetime.now().date()
        # options = {'unfolded_lines': [],
        #            'date': {'string': 'As of 18/05/2022', 'period_type': 'today', 'mode': 'single', 'strict_range': False,
        #                     'date_from': '2022-05-01', 'date_to': date_to, 'filter': 'today'},
        #                     'partner': True, 'partner_ids': [], 'partner_categories': [], 'selected_partner_ids': [],
        #            'selected_partner_categories': [], 'unfold_all': False, 'selected_column': 0,
        #            'filter_account_type': 'payable'}
        options = self.env['account.aged.payable'].sudo()._get_options(previous_options=None)
        # period_table = self._get_query_period_table(options)
        query = ("""
                       SELECT
                           {move_line_fields},
                           account_move_line.partner_id AS partner_id,
                           partner.name AS partner_name,
                           COALESCE(trust_property.value_text, 'normal') AS partner_trust,
                           COALESCE(account_move_line.currency_id, journal.currency_id) AS report_currency_id,
                           account_move_line.payment_id AS payment_id,
                           COALESCE(account_move_line.date_maturity, account_move_line.date) AS report_date,
                           account_move_line.expected_pay_date AS expected_pay_date,
                           move.move_type AS move_type,
                           move.name AS move_name,
                           journal.code AS journal_code,
                           account.name AS account_name,
                           account.code AS account_code,""" + ','.join([("""
                           CASE WHEN period_table.period_index = {i}
                           THEN %(sign)s * ROUND((
                               account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0)
                           ) * currency_table.rate, currency_table.precision)
                           ELSE 0 END AS period{i}""").format(i=i) for i in range(6)]) + """
                       FROM account_move_line
                       JOIN account_move move ON account_move_line.move_id = move.id
                       JOIN account_journal journal ON journal.id = account_move_line.journal_id
                       JOIN account_account account ON account.id = account_move_line.account_id
                       JOIN res_partner partner ON partner.id = account_move_line.partner_id
                       LEFT JOIN ir_property trust_property ON (
                           trust_property.res_id = 'res.partner,'|| account_move_line.partner_id
                           AND trust_property.name = 'trust'
                           AND trust_property.company_id = account_move_line.company_id
                       )
                       JOIN {currency_table} ON currency_table.company_id = account_move_line.company_id
                       LEFT JOIN LATERAL (
                           SELECT part.amount, part.debit_move_id
                           FROM account_partial_reconcile part
                           WHERE part.max_date <= %(date)s
                       ) part_debit ON part_debit.debit_move_id = account_move_line.id
                       LEFT JOIN LATERAL (
                           SELECT part.amount, part.credit_move_id
                           FROM account_partial_reconcile part
                           WHERE part.max_date <= %(date)s
                       ) part_credit ON part_credit.credit_move_id = account_move_line.id
                       JOIN {period_table} ON (
                           period_table.date_start IS NULL
                           OR COALESCE(account_move_line.date_maturity, account_move_line.date) <= DATE(period_table.date_start)
                       )
                       AND (
                           period_table.date_stop IS NULL
                           OR COALESCE(account_move_line.date_maturity, account_move_line.date) >= DATE(period_table.date_stop)
                       )
                       WHERE account.internal_type = %(account_type)s and move.state = 'posted'
                       GROUP BY account_move_line.id, partner.id, trust_property.id, journal.id, move.id, account.id,
                                period_table.period_index, currency_table.rate, currency_table.precision
                       HAVING ROUND(account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0), currency_table.precision) != 0
                   """).format(
            move_line_fields=self._get_move_line_fields('account_move_line'),
            currency_table=self.env['res.currency']._get_query_currency_table(options),
            period_table=self._get_query_period_table(options),
        )
        params = {
            'account_type': options['filter_account_type'],
            'sign': 1 if options['filter_account_type'] == 'receivable' else -1,
            'date': date_to,
        }
        query = self.env.cr.mogrify(query, params).decode(self.env.cr.connection.encoding)
        self.env.cr.execute(query)
        data = self.env.cr.fetchall()
        payable_data = {'as_on': 0, 'p1': 0, 'p2': 0, 'p3': 0, 'p4': 0, 'older': 0}
        for rec in data:
            # move = self.env['account.move'].sudo().search([('id', '=', rec[1]), ('state', '=', 'posted'), ('invoice_date', '>=', from_date)
            #         , ('invoice_date', '<=', to_date)])
            # if move:
            payable_data['as_on'] = round((payable_data['as_on'] + rec[-6]), 2)
            payable_data['p1'] = round((payable_data['p1'] + rec[-5]), 2)
            payable_data['p2'] = round((payable_data['p2'] + rec[-4]), 2)
            payable_data['p3'] = round((payable_data['p3'] + rec[-3]), 2)
            payable_data['p4'] = round((payable_data['p4'] + rec[-2]), 2)
            payable_data['older'] = round((payable_data['older'] + rec[-1]), 2)

        return payable_data


class MoveLines(models.Model):
    _inherit = 'stock.move.line'

    def non_moving_products(self):
        today = datetime.today()
        # last_year = today - datetime.timedelta(days=365)
        last_year = today - relativedelta(months=12)
        data = []
        moving_prods = self.sudo().read_group(
            [('move_id.state', '=', 'done'), ('product_id.type', '=', 'product'), ('move_id.date', '>', last_year)],
            fields=['product_id.display_name', 'date:min'],
            groupby=['product_id'], orderby="date asc")

        prod_names = []
        for rec in moving_prods:
            prod_names.append(rec['product_id'][1])

        non_moving = self.sudo().read_group([('move_id.state', '=', 'done'), ('product_id.type', '=', 'product'),
                                             ('product_id.name', 'not in', prod_names),
                                             ('move_id.date', '<', last_year)],
                                            fields=['product_id.display_name', 'date:min'],
                                            groupby=['product_id'], orderby="date asc", limit=5)

        for rec in non_moving:
            recent_move = self.sudo().search(
                [('move_id.state', '=', 'done'), ('product_id.id', '=', rec['product_id'][0])], order='date desc',
                limit=1)
            non_moving_days = (today - recent_move.move_id.date).days
            data.append({'product': rec['product_id'][1], 'days': str(non_moving_days),
                         'qty': str(recent_move.product_id.qty_available)})
        return data

    def slow_moving_products(self):
        today = datetime.today()
        # six_month = today - datetime.timedelta(days=180)
        six_month = today - relativedelta(months=6)
        # twelve_month = today - datetime.timedelta(days=365)
        twelve_month = today - relativedelta(months=12)
        data = []
        prods_to_exclude = self.sudo().read_group(
            [('move_id.state', '=', 'done'), ('product_id.type', '=', 'product'), '|',
             ('move_id.date', '<', twelve_month), ('move_id.date', '>', six_month)],
            fields=['product_id.display_name', 'date:min'],
            groupby=['product_id'], orderby="date:min ASC")
        prod_names = []
        for rec in prods_to_exclude:
            prod_names.append(rec['product_id'][1])

        slow_moving = self.sudo().read_group([('move_id.state', '=', 'done'), ('product_id.type', '=', 'product'),
                                              ('product_id.name', 'not in', prod_names),
                                              ('move_id.date', '>=', twelve_month), ('move_id.date', '<=', six_month)],
                                             fields=['product_id.display_name'], groupby=['product_id'],
                                             orderby="date:min ASC", limit=5)

        for rec in slow_moving:
            recent_move = self.sudo().search(
                [('move_id.state', '=', 'done'), ('product_id.id', '=', rec['product_id'][0])], order='date desc',
                limit=1)
            slow_moving_days = (today - recent_move.move_id.date).days
            data.append({'product': rec['product_id'][1], 'days': str(slow_moving_days),
                         'qty': str(recent_move.product_id.qty_available)})
        return data
        # return data


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    # def get_opening_closing_values(self):
    #     today = datetime.date.today()
    #     yesterday =  today - relativedelta(days= 1)
    #     today_max = datetime.datetime.combine(today, datetime.datetime.max.time())
    #
    #     yesterday_max = datetime.datetime.combine(yesterday, datetime.datetime.max.time())
    #
    #     opening = self.sudo().read_group([('create_date', '<=', yesterday_max)],fields=['total_value:sum(value)'],groupby=[])
    #     closing = self.sudo().read_group([('create_date', '<=', today_max)],fields=['total_value:sum(value)'],groupby=[])
    #
    #     return {'opening':round(opening[0]['total_value'],2),'closing':round(closing[0]['total_value'],2)}

    def get_top_sold_cell_val(self):
        result = self.sudo().read_group(
            [('product_id', '!=', False), ('product_id.product_type', '=', 'cell'), ('create_date', '>=', from_date)
                , ('create_date', '<=', to_date), ('quantity', '<', 0)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(value)'],
            groupby=['product_id'], orderby="total_price DESC", limit=5)
        data = []
        for rec in result:
            data.append({'product_name': rec['product_id'][1], 'total_quantity': -rec['total_quantity'],
                         'total_price': -round(rec['total_price'], 2)})
        return data

    def get_top_sold_cell_vol(self):
        result = self.sudo().read_group(
            [('product_id', '!=', False), ('product_id.product_type', '=', 'cell'), ('create_date', '>=', from_date)
                , ('create_date', '<=', to_date), ('quantity', '<', 0)],
            fields=['product_id.name', 'total_quantity:sum(quantity)', 'total_price:sum(value)'],
            groupby=['product_id'], orderby="total_quantity DESC", limit=5)
        data = []
        for rec in result:
            data.append({'product_name': rec['product_id'][1], 'total_quantity': -rec['total_quantity'],
                         'total_price': -round(rec['total_price'], 2)})
        return data


# useless
# class ReportAccountFinancialReport(models.Model):
#     _inherit = "account.financial.html.report"
#
#     def get_pnl_report(self):
#         options = self._get_options(previous_options=None)
#         res = self._get_lines(options, line_id=None)
#         return res


class SaleOrderReport(models.Model):
    _inherit = 'sale.order'

    def get_pending_so(self):
        # pending qty logic based on MO
        # orders = self.sudo().search([('state','=','done')])
        # pending_amount = 0.0
        # for order in orders:
        #     mos = self.env['mrp.production'].sudo().search([('procurement_group_id.mrp_production_ids.move_dest_ids.group_id.sale_id.id','=',order.id),('state','not in',('done','cancel'))])
        #     if mos:
        #         pending_amount += order.amount_total
        # return pending_amount
        orders = self.env['sale.order'].search([('state', '=', 'approved')])
        pending_qty = 0.0
        pending_amount = 0.0
        for order in orders:
            for line in order.order_line:
                if line.qty_delivered < line.product_uom_qty:
                    pending_qty += line.product_uom_qty - line.qty_delivered
                    pending_amount += (line.product_uom_qty - line.qty_delivered) * line.price_unit
        return {'qty': pending_qty, 'amount': pending_amount}


class PurchaseOrderReport(models.Model):
    _inherit = 'purchase.order'

    def get_pending_po(self):
        orders = self.env['purchase.order'].search([('receipt_status', '=', 'pending')])
        pending_qty = 0.0
        pending_amount = 0.0
        for order in orders:
            for line in order.order_line:
                if line.qty_received < line.product_qty:
                    pending_qty += line.product_qty - line.qty_received
                    pending_amount += (line.product_qty - line.qty_received) * line.price_unit
        return {'qty': pending_qty, 'amount': pending_amount}


class DateWisePOReportPdf(models.TransientModel):
    _name = 'po.daily.report'
    _description = 'po daily report'

    to_date = fields.Date()
    currency_id = fields.Many2one('res.currency', default=20)

    # def print_daily_report(self):
    #     return self.env.ref('po_daily_report.action_download_daily_report').report_action(self)

    @classmethod
    def _generate_options(cls, report, date_from, date_to, default_options=None):
        ''' Create new options at a certain date.
        :param report:          The report.
        :param date_from:       A datetime object, str representation of a date or False.
        :param date_to:         A datetime object or str representation of a date.
        :return:                The newly created options.
        '''
        if isinstance(date_from, datetime):
            date_from_str = fields.Date.to_string(date_from)
        else:
            date_from_str = date_from

        if isinstance(date_to, datetime):
            date_to_str = fields.Date.to_string(date_to)
        else:
            date_to_str = date_to

        if not default_options:
            default_options = {}

        return report.get_options({
            'selected_variant_id': report.id,
            'date': {
                'date_from': date_from_str,
                'date_to': date_to_str,
                'mode': 'range',
                'filter': 'custom',
            },
            **default_options,
        })

    def get_opening_closing_values(self):
        today = datetime.today().date()
        yesterday = today - relativedelta(days=1)
        today_max = datetime.combine(today, datetime.max.time())

        yesterday_max = datetime.combine(yesterday, datetime.max.time())
        products = self.env['product.product'].sudo().search([('active', '=', True)])
        opening_products = products.with_context(to_date=yesterday_max)
        closing_products = products.with_context(to_date=today_max)
        opening_value = sum([product.value_svl for product in opening_products])
        closing_value = sum([product.value_svl for product in closing_products])

        return {'opening': round(opening_value, 2), 'closing': round(closing_value, 2)}

    def send_daily_stock_reports(self):
        # pnl_data = self.env['account.financial.html.report'].sudo().get_pnl_report()
        # cash_flow = self.env['account.move.line'].sudo().get_cash_flow()
        top_customer = self.env['account.move'].sudo().get_top_customer(),
        top_supplier = self.env['account.move'].sudo().get_top_supplier(),
        top_os_customer = self.env['account.move'].sudo().top_os_customer(),
        top_os_supplier = self.env['account.move'].sudo().top_os_supplier(),
        top_over_due_customer = self.env['account.move'].sudo().top_over_due_customer(),
        top_over_due_supplier = self.env['account.move'].sudo().top_over_due_supplier(),
        top_sold_battery_vol = self.env['account.move.line'].sudo().get_top_sold_battery_vol(),
        top_sold_cell_vol = self.env['stock.valuation.layer'].sudo().get_top_sold_cell_vol(),
        top_sold_battery_val = self.env['account.move.line'].sudo().get_top_sold_battery_val(),
        top_sold_cell_val = self.env['stock.valuation.layer'].sudo().get_top_sold_cell_val(),
        top_purchased_battery_vol = self.env['account.move.line'].sudo().get_top_purchased_battery_vol(),
        top_purchased_cell_vol = self.env['account.move.line'].sudo().get_top_purchased_cell_vol(),
        top_purchased_battery_val = self.env['account.move.line'].sudo().get_top_purchased_battery_val(),
        top_purchased_cell_val = self.env['account.move.line'].sudo().get_top_purchased_cell_val(),
        bank_data = self.env['account.journal'].sudo().get_bank_data(),
        age_receivable_report = self.env.ref('account_reports.aged_receivable_report')
        age_receivable = self.env[
            'account.aged.partner.balance.report.handler'].sudo()._aged_partner_report_custom_engine_common(
            options=self._generate_options(age_receivable_report, date_from=None, date_to=fields.Date.today(),
                                           default_options={'assets_groupby_account': False, 'unfold_all': False,
                                                            'all_entries': True}), internal_type='asset_receivable',
            current_groupby=None, next_groupby='partner_id,id',
            offset=0, limit=None),
        age_payable_report = self.env.ref('account_reports.aged_payable_report')
        age_payable = self.env['account.aged.partner.balance.report.handler'].sudo()._aged_partner_report_custom_engine_common(
            options=self._generate_options(age_payable_report, date_from=None, date_to=fields.Date.today(),
                                           default_options={'assets_groupby_account': False, 'unfold_all': False,
                                                            'all_entries': True}), internal_type='liability_payable',
            current_groupby=None, next_groupby='partner_id,id',
            offset=0, limit=None),
        # pending_so_val= sum(self.env['sale.order'].search([('state', 'in', ['draft', 'sent'])]).mapped('amount_untaxed')),
        pending_so_val = self.env['sale.order'].sudo().get_pending_so(),
        pending_po_val = self.env['purchase.order'].sudo().get_pending_po(),
        cash_bank_balances = self.env['account.move.line'].sudo().get_cash_bank_balance()
        non_moving_products = self.env['stock.move.line'].sudo().non_moving_products()
        slow_moving_products = self.env['stock.move.line'].sudo().slow_moving_products()
        stock_values = self.get_opening_closing_values()
        sales_purchase = self.env['account.move'].sudo().get_sales_purchases()
        users = self.env['res.users'].sudo().search([])

        body = """Hello Team,
                    <br/><p>Please refer to the valuation report given below:</p>
                    """
        if age_payable and age_receivable:
            age_payable = age_payable[0]
            age_receivable = age_receivable[0]
            body += """<br/><p><b>Aged Receivable/Payable</b></p>
                            <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                            <thead>
                                <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th align="center" style="border: 1px solid black;color:white;">Age Wise</th>
                                    <th align="center" style="border: 1px solid black;color:white;">Debtors</th>
                                    <th align="center" style="border: 1px solid black;color:white;">Creditors</th>
                                <tr>
                            </thead>
                            <tbody>
                                <tr align="center" style="border: 1px solid">
                                    <td align="left" style="border: 1px solid">As of: """ + datetime.strftime(
                today, "%d/%m/%Y") + """ (Non-due)</td>
                                    <td align="right" style="border: 1px solid">{recv_as_on}</td>
                                    <td align="right" style="border: 1px solid">{pay_as_on}</td>
                                </tr>
                                <tr align="center" style="border: 1px solid">
                                    <td align="left" style="border: 1px solid">1-30 (Over-due)</td>
                                    <td align="right" style="border: 1px solid">{recv_p1}</td>
                                    <td align="right" style="border: 1px solid">{pay_p1}</td>
                                </tr>
                                <tr align="center" style="border: 1px solid">
                                    <td align="left" style="border: 1px solid">31-60 (Over-due)</td>
                                    <td align="right" style="border: 1px solid">{recv_p2}</td>
                                    <td align="right" style="border: 1px solid">{pay_p2}</td>
                                </tr>
                                <tr align="center" style="border: 1px solid">
                                    <td align="left" style="border: 1px solid">61-90 (Over-due)</td>
                                    <td align="right" style="border: 1px solid">{recv_p3}</td>
                                    <td align="right" style="border: 1px solid">{pay_p3}</td>
                                </tr>
                                <tr align="center" style="border: 1px solid">
                                    <td align="left" style="border: 1px solid">91-120 (Over-due)</td>
                                    <td align="right" style="border: 1px solid">{recv_p4}</td>
                                    <td align="right" style="border: 1px solid">{pay_p4}</td>
                                </tr>
                                <tr align="center" style="border: 1px solid">
                                    <td align="left" style="border: 1px solid">Older (Over-due)</td>
                                    <td align="right" style="border: 1px solid">{recv_older}</td>
                                    <td align="right" style="border: 1px solid">{pay_older}</td>
                                </tr>
                            </tbody>
                        </table>
                            """.format(recv_as_on=format_currency(age_receivable['as_on'], 'INR', locale='en_IN'),
                                       pay_as_on=format_currency(age_payable['as_on'], 'INR', locale='en_IN'),
                                       recv_p1=format_currency(age_receivable['p1'], 'INR', locale='en_IN'),
                                       pay_p1=format_currency(age_payable['p1'], 'INR', locale='en_IN'),
                                       recv_p2=format_currency(age_receivable['p2'], 'INR', locale='en_IN'),
                                       pay_p2=format_currency(age_payable['p2'], 'INR', locale='en_IN'),
                                       recv_p3=format_currency(age_receivable['p3'], 'INR', locale='en_IN'),
                                       pay_p3=format_currency(age_payable['p3'], 'INR', locale='en_IN'),
                                       recv_p4=format_currency(age_receivable['p4'], 'INR', locale='en_IN'),
                                       pay_p4=format_currency(age_payable['p4'], 'INR', locale='en_IN'),
                                       recv_older=format_currency(age_receivable['older'], 'INR', locale='en_IN'),
                                       pay_older=format_currency(age_payable['older'], 'INR', locale='en_IN'))

        if top_customer and top_supplier:
            body += """ <br/>
                        <p><b>Top 5 Customers</b></p>
                        <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                            <thead>
                                <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th colspan="2" align="center" style="border: 1px solid black;color:white;"> Top 5 Customers</th>
                                <tr>
                            </thead>
                            <tbody>
                            """
            for tc in top_customer[0]:
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=tc['partner_name']._value,
                                   amount=format_currency(tc['amount_total'], 'INR', locale='en_IN'))
            body += """</tbody></table><br/>
                        <p><b>Top 5 Suppliers</b></p>
                        <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                            <thead>
                                <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th colspan="2" align="center" style="border: 1px solid black;color:white;"> Top 5 Suppliers</th>
                                <tr>
                            </thead>
                            <tbody>"""
            for ts in top_supplier[0]:
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=ts['partner_name']._value,
                                   amount=format_currency(ts['amount_total'], 'INR', locale='en_IN'))

            body += """</tbody></table>"""

        if top_os_customer and top_os_supplier:
            body += """<br/>
                    <p><b>Top 10 Customers (O/S Receivables)</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th colspan="2" align="center" style="border: 1px solid black;color:white;">Top 10 Customers (O/S Receivables)</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for toc in top_os_customer[0]:
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=toc['partner_name']._value,
                                   amount=format_currency(toc['total_amount_residual'], 'INR', locale='en_IN'))

            body += """</tbody></table><br/>
                            <p><b>Top 10 Suppliers (O/S Payable)</b></p>
                            <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                                <thead>
                                    <tr style="border: 1px solid; background-color:#2f756f;">
                                        <th colspan="2" align="center" style="border: 1px solid black;color:white;">Top 10 Suppliers (O/S Payable)</th>
                                    <tr>
                                </thead>
                                <tbody>"""
            for tos in top_os_supplier[0]:
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=tos['partner_name']._value,
                                   amount=format_currency(tos['total_amount_residual'], 'INR', locale='en_IN'))

            body += """</tbody></table>"""

        if pending_so_val and pending_po_val:
            body += """<br/>
                    <p><b>Pending Sales Order (In Value)</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Pending Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Pending Amount</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr align="center" style="border: 1px solid">
                                <td align="center" style="border: 1px solid">{pending_so_qty}</td>
                                <td align="center" style="border: 1px solid">{pending_so_amount}</td>
                            </tr>
                        </tbody>
                    </table><br/>
                    <p><b>Pending Purchase Order (In Value)</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Pending Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Pending Amount</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr align="center" style="border: 1px solid">
                                <td align="center" style="border: 1px solid">{pending_po_qty}</td>
                                <td align="center" style="border: 1px solid">{pending_po_amount}</td>
                            </tr>
                        </tbody>
                    </table>""".format(pending_so_qty=pending_so_val[0]['qty'],
                                       pending_so_amount=format_currency(pending_so_val[0]['amount'], 'INR',
                                                                         locale='en_IN'),
                                       pending_po_qty=pending_po_val[0]['qty'],
                                       pending_po_amount=format_currency(pending_po_val[0]['amount'], 'INR',
                                                                         locale='en_IN'))

        if bank_data:
            bank_data = bank_data[0]
            body += """ <br/>
                        <p><b>Bank Details</b></p>
                        <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                            <thead>
                                <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th colspan="2" align="center" style="border: 1px solid black;color:white;"> Bank Details </th>
                                </tr>
                                <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th align="center" style="border: 1px solid black;color:white;"> Bank Name </th>
                                    <th align="center" style="border: 1px solid black;color:white;"> Balance
                                     </th>
                                </tr>
                            </thead>
                            <tbody>
                    """
            for bd in bank_data:
                body += """
                            <tr align="center" style="border: 1px solid">
                                <td align="left" style="border: 1px solid">{name}</td>
                                <td align="right" style="border: 1px solid">{amount}</td>
                            </tr>""".format(name=bd[0], amount=format_currency(bd[1], 'INR', locale='en_IN'))
            body += """</tbody>
                        </table>
                    """

        # if cash_flow:
        #     body += """
        #             <br/>
        #             <p><b>Cash Flow</b></p>
        #             <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
        #             <tbody>
        #                 <tr align="center" style="border: 1px solid">
        #                     <th align="left" style="border: 1px solid">In Flow :</th>
        #                     <td align="right" style="border: 1px solid">{total_credit}</td>
        #                 </tr>
        #                 <tr align="center" style="border: 1px solid">
        #                     <th align="left" style="border: 1px solid">Out Flow :</th>
        #                     <td align="right" style="border: 1px solid">{total_debit}</td>
        #                 </tr>
        #             </tbody>
        #         </table>
        #         """.format(total_credit=format_currency(cash_flow['total_credit'], 'INR',locale='en_IN'),total_debit=format_currency(cash_flow['total_debit'], 'INR',locale='en_IN'))

        if cash_bank_balances:
            body += """
                        <br/>
                        <p><b>Cash & Bank Balances</b></p>
                        <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                            <thead>
                                <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th align="center" style="border: 1px solid black;color:white;">Account</th>
                                    <th align="center" style="border: 1px solid black;color:white;">Balance</th>
                                </tr>
                            </thead>
                            <tbody>
                        """
            for cash_bank_balance in cash_bank_balances:
                test = cash_bank_balance['account_name']._value
                body += """
                                    <tr align="center" style="border: 1px solid">
                                        <td align="left" style="border: 1px solid">{name}</td>
                                        <td align="right" style="border: 1px solid">{amount}</td>
                                    </tr>
                                    """.format(name=cash_bank_balance['account_name']._value,
                                               amount=format_currency(cash_bank_balance['balance'], 'INR',
                                                                      locale='en_IN'))
            body += """</tbody>
                        </table>
                    """
        if top_sold_battery_val and top_sold_cell_val:
            body += """
                    <br/>
                    <p><b>Top 5 Batteries ( Sold in Value )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Battery Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for sold_battery_val in top_sold_battery_val[0]:
                product = sold_battery_val['product']
                prod_desc = str(product.name) + " [" + "Cell Type:" + str(product.cell_type.name) + ", Volts:" + str(
                    product.volts) + ", AH:" + str(product.ah) + "]"
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{total_qty}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=prod_desc,
                                   amount=format_currency(sold_battery_val['total_price'], 'INR', locale='en_IN'),
                                   total_qty=sold_battery_val['total_quantity'])
            body += """
                    </tbody></table><br/>
                    <p><b>Top 5 Cells ( Sold in Value )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Cell Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for top_sold_cell in top_sold_cell_val[0]:
                body += """
                                        <tr align="center" style="border: 1px solid">
                                            <td align="left" style="border: 1px solid">{name}</td>
                                            <td align="right" style="border: 1px solid">{qty}</td>
                                            <td align="right" style="border: 1px solid">{amount}</td>
                                        </tr>
                                        """.format(name=top_sold_cell['product_name']._value,
                                                   qty=top_sold_cell['total_quantity'],
                                                   amount=format_currency(top_sold_cell['total_price'], 'INR',
                                                                          locale='en_IN'))

            body += """</tbody></table>"""

        if top_sold_battery_vol and top_sold_cell_vol:
            body += """
                    <br/>
                    <p><b>Top 5 Batteries ( Sold in Volume )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Battery Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for sold_battery_vol in top_sold_battery_vol[0]:
                product = sold_battery_vol['product']
                prod_desc = str(product.name) + " [" + "Cell Type:" + str(product.cell_type.name) + ", Volts:" + str(
                    product.volts) + ", AH:" + str(product.ah) + "]"
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{qty}</td>
                            <td align="right" style="border: 1px solid">{value}</td>
                        </tr>
                        """.format(name=prod_desc, qty=sold_battery_vol['total_quantity'],
                                   value=sold_battery_vol['total_price'])
            body += """
                    </tbody></table><br/>
                    <p><b>Top 5 Cells ( Sold in Volume )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Cell Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for sold_cell_vol in top_sold_cell_vol[0]:
                body += """
                                        <tr align="center" style="border: 1px solid">
                                            <td align="left" style="border: 1px solid">{name}</td>
                                            <td align="right" style="border: 1px solid">{qty}</td>
                                            <td align="right" style="border: 1px solid">{value}</td>
                                        </tr>
                                        """.format(name=sold_cell_vol['product_name']._value,
                                                   qty=sold_cell_vol['total_quantity'],
                                                   value=sold_cell_vol['total_price'])

            body += """</tbody></table>"""

        if top_purchased_battery_val and top_purchased_cell_val:
            body += """
                    <br/>
                    <p><b>Top 5 Batteries ( Purchased in Value )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Battery Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for purchased_battery_val in top_purchased_battery_val[0]:
                product = purchased_battery_val['product']
                prod_desc = str(product.name) + " [" + "Cell Type:" + str(product.cell_type.name) + ", Volts:" + str(
                    product.volts) + ", AH:" + str(product.ah) + "]"
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{total_quantity}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=prod_desc,
                                   amount=format_currency(purchased_battery_val['total_price'], 'INR', locale='en_IN'),
                                   total_quantity=purchased_battery_val['total_quantity'])
            body += """
                    </tbody></table><br/>
                    <p><b>Top 5 Cells ( Purchased in Value )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Cell Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for purchased_cell_val in top_purchased_cell_val[0]:
                body += """
                                        <tr align="center" style="border: 1px solid">
                                            <td align="left" style="border: 1px solid">{name}</td>
                                            <td align="right" style="border: 1px solid">{total_quantity}</td>
                                            <td align="right" style="border: 1px solid">{amount}</td>
                                        </tr>
                                        """.format(name=purchased_cell_val['product_name']._value,
                                                   amount=format_currency(purchased_cell_val['total_price'], 'INR',
                                                                          locale='en_IN'),
                                                   total_quantity=purchased_cell_val['total_quantity'])

            body += """</tbody></table>"""

        if top_purchased_battery_vol and top_purchased_cell_vol:
            body += """
                    <br/>
                    <p><b>Top 5 Batteries ( Purchased in Volume )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Battery Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for purchased_battery_vol in top_purchased_battery_vol[0]:
                product = purchased_battery_vol['product']
                prod_desc = str(product.name) + " [" + "Cell Type:" + str(product.cell_type.name) + ", Volts:" + str(
                    product.volts) + ", AH:" + str(product.ah) + "]"
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{qty}</td>
                            <td align="right" style="border: 1px solid">{value}</td>
                        </tr>
                        """.format(name=prod_desc, qty=purchased_battery_vol['total_quantity'],
                                   value=purchased_battery_vol['total_price'])
            body += """
                    </tbody></table><br/>
                    <p><b>Top 5 Cells ( Purchased in Volume )</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Cell Name</th>
                                <th align="center" style="border: 1px solid black;color:white;">Qty</th>
                                <th align="center" style="border: 1px solid black;color:white;">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for purchased_cell_vol in top_purchased_cell_vol[0]:
                body += """
                                        <tr align="center" style="border: 1px solid">
                                            <td align="left" style="border: 1px solid">{name}</td>
                                            <td align="right" style="border: 1px solid">{qty}</td>
                                            <td align="right" style="border: 1px solid">{value}</td>
                                        </tr>
                                        """.format(name=purchased_cell_vol['product_name']._value,
                                                   qty=purchased_cell_vol['total_quantity'],
                                                   value=purchased_cell_vol['total_price'])

            body += """</tbody></table>"""

        if sales_purchase:
            body += """<br/>
                        <p><b>Turnover-Sales & Purchase</b></p>
                        <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Sales Accounts</td>
                                <th align="center" style="border: 1px solid black;color:white;">Purchase Accounts</td>
                            </tr>
                        </thead>
                        <tbody>
                            <tr align="center" style="border: 1px solid">
                                <td align="left" style="border: 1px solid">{sales}</td>
                                <td align="right" style="border: 1px solid">{purchase}</td>
                            </tr>
                        </tbody></table><br/>""".format(
                sales=format_currency(sales_purchase['sales'], 'INR', locale='en_IN'),
                purchase=format_currency(sales_purchase['purchase'], 'INR', locale='en_IN'))

        if slow_moving_products and non_moving_products:
            body += """<br/>
                        <p><b>Top 5 Non Moving Items</b></p>
                        <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                            <thead>
                                <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th align="center" style="border: 1px solid black;color:white;">Product</th>
                                    <th align="center" style="border: 1px solid black;color:white;">Latest move before</th>
                                    <th align="center" style="border: 1px solid black;color:white;">Available Quantity</th>
                                </tr>
                            </thead>
                            <tbody>
                        """
            for non_moving_product in non_moving_products:
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="center" style="border: 1px solid">{name}</td>
                            <td align="center" style="border: 1px solid">{days} Days</td>
                            <td align="center" style="border: 1px solid">{qty}</td>
                        </tr>
                        """.format(name=non_moving_product['product']._value, days=non_moving_product['days'],
                                   qty=non_moving_product['qty'])
            body += """
                    </tbody></table><br/>
                    <p><b>Top 5 Slow Moving Items</b></p>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                    <th align="center" style="border: 1px solid black;color:white;">Product</th>
                                    <th align="center" style="border: 1px solid black;color:white;">Latest move before</th>
                                    <th align="center" style="border: 1px solid black;color:white;">Available Quantity</th>                            </tr>
                        </thead>
                        <tbody>
                    """
            for slow_moving_product in slow_moving_products:
                body += """
                            <tr align="center" style="border: 1px solid">
                                <td align="center" style="border: 1px solid">{name}</td>
                                <td align="center" style="border: 1px solid">{days} Days</td>
                                <td align="center" style="border: 1px solid">{qty}</td>
                            </tr>
                            """.format(name=slow_moving_product['product']._value,
                                       days=slow_moving_product['days'], qty=slow_moving_product['qty'])

            body += """</tbody></table>"""

        if stock_values:
            body += """<br/>
                        <p><b>Stock Value</b></p>
                        <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                         <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th align="center" style="border: 1px solid black;color:white;">Opening Stock</td>
                                <th align="center" style="border: 1px solid black;color:white;">Closing Stock</td>
                            </tr>
                        </thead>
                        <tbody>
                            <tr align="center" style="border: 1px solid">
                                <td align="left" style="border: 1px solid">{opening}</td>
                                <td align="right" style="border: 1px solid">{closing}</td>
                            </tr>
                        </tbody>
                        </table><br/>""".format(opening=format_currency(stock_values['opening'], 'INR', locale='en_IN'),
                                                closing=format_currency(stock_values['closing'], 'INR', locale='en_IN'))

        if top_over_due_customer and top_over_due_supplier:
            body += """<br/>
                    <table style="width: 100%;border: 3px solid;border-collapse:collapse;">
                        <thead>
                            <tr style="border: 1px solid; background-color:#2f756f;">
                                <th colspan="2" align="center" style="border: 1px solid black;color:white;">Top 10 Customers (OverDue Bills)</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
            for todc in top_over_due_customer[0]:
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid">{name}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=todc['partner_name']._value,
                                   amount=format_currency(todc['total_amount_residual'], 'INR', locale='en_IN'))

            body += """</tbody></table><br/>
                            <table style="width: 100%;border: 1px solid;border-collapse:collapse;">
                                <thead>
                                    <tr style="border: 1px solid; background-color:#2f756f;">
                                        <th colspan="2" align="center" style="border: 1px solid black;color:white;">Top 10 Suppliers (OverDue Bills)</th>
                                    <tr>
                                </thead>
                                <tbody>"""
            for tods in top_over_due_supplier[0]:
                body += """
                        <tr align="center" style="border: 1px solid">
                            <td align="left" style="border: 1px solid;">{name}</td>
                            <td align="right" style="border: 1px solid">{amount}</td>
                        </tr>
                        """.format(name=tods['partner_name']._value,
                                   amount=format_currency(tods['total_amount_residual'], 'INR', locale='en_IN'))

            body += """</tbody></table><br/>
                    <p><b>Due Invoices</b></p>
                    <table style="width:100%;border: 1px solid;border-collapse:collapse;">
                                <thead>
                                    <tr style="border: 1px solid; background-color:#2f756f;">
                                        <th align="center" style="border: 1px solid black;color:white;">Customer Name</th>
                                        <th align="center" style="border: 1px solid black;color:white;">Invoice Number</th>
                                        <th align="center" style="border: 1px solid black;color:white;">Invoice Date</th>
                                        <th align="center" style="border: 1px solid black;color:white;">Credit Period</th>
                                        <th align="center" style="border: 1px solid black;color:white;">Due Date</th>
                                        <th align="center" style="border: 1px solid black;color:white;">Overdue Days</th>
                                        <th align="center" style="border: 1px solid black;color:white;">Due Amount</th>
                                    </tr>
                                </thead>
                                <tbody>"""
            invoices = self.env['account.move'].sudo().search(
                [('amount_residual', '>', 0), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted')])
            inv_list = []
            for inv in invoices:
                overdue_days = ((
                                        datetime.date.today() - inv.invoice_date_due).days) if datetime.date.today() > inv.invoice_date_due else 0
                inv_list.append({'overdue_days': overdue_days, 'inv': inv})
            if inv_list:
                inv_list.sort(key=operator.itemgetter('overdue_days'), reverse=True)

            for invoice in inv_list:
                inv = invoice.get('inv')
                amount_residual = inv.currency_id._convert(inv.amount_residual, inv.company_id.currency_id,
                                                           inv.company_id, inv.invoice_date, round=False)
                body += """
                            <tr align="center" style="border: 1px solid">
                                <td align="left" style="border: 1px solid">{partner}</td>
                                <td align="left" style="border: 1px solid">{name}</td>
                                <td align="left" style="border: 1px solid">{invoice_date}</td>
                                <td align="left" style="border: 1px solid">{credit_period}</td>
                                <td align="left" style="border: 1px solid">{due_date}</td>
                                <td align="left" style="border: 1px solid">{overdue_days}</td>
                                <td align="right" style="border: 1px solid">{due_amount_lc}</td>
                                <td align="right" style="border: 1px solid">{due_amount_fc}</td>
                            </tr>
                                    """.format(partner=inv.partner_id.name or inv.partner_id.display_name,
                                               name=inv.name,
                                               invoice_date=datetime.date.strftime(inv.invoice_date, "%d/%m/%Y"),
                                               credit_period=inv.invoice_payment_term_id.name,
                                               due_date=datetime.date.strftime(inv.invoice_date_due, "%d/%m/%Y"),
                                               overdue_days=str(invoice.get('overdue_days')) + " Days",
                                               due_amount_lc=format_currency(amount_residual, 'INR', locale='en_IN'),
                                               due_amount_fc=self._format_currency_amount(inv.currency_id,
                                                                                          inv.amount_residual), )
            body += """</tbody></table>"""

        for user in users:
            if user.has_group('gts_daily_analysis_email_report.group_daily_analysis_report_access'):
                mail = self.env['mail.mail'].sudo().create({
                    'subject': """Company Valuation Report""",
                    'email_to': user.login,
                    # 'email_to': "nitin@planet-odoo.com",
                    'email_from': "odoo@eternitytechnologies.com",
                    'email_cc': "milind.deshpande@eternitytechnologies.com",
                    'reply_to': user.login,
                    'body_html': body
                })
                mail.send()
