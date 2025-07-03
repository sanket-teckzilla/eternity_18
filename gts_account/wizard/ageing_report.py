from odoo import models, api, _, fields
from datetime import datetime
from odoo.exceptions import ValidationError
from itertools import chain
from dateutil.relativedelta import relativedelta
from odoo.tools import float_is_zero, float_compare
import xlwt
import base64
from io import BytesIO

class AgeingReport(models.TransientModel):
    _name = 'po.ageing.report'
    _description = 'po ageing report'

    duration = fields.Integer("Duration",default=30)
    state = fields.Selection([('choose', 'choose'), ('get', 'get')], default='choose')
    report_type = fields.Selection([('receivable','Receivable'),('payable','Payable')])
    report_file = fields.Binary()
    filename = fields.Char()
    end_date = fields.Date("End Date",default=fields.Date.today)

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
        date_str = self.end_date
        date = fields.Date.from_string(date_str)
        period_values = [
            (False, date_str),
            (minus_days(date, 1), minus_days(date, (self.duration or 30))),
            (minus_days(date, (self.duration or 30)+1), minus_days(date, (self.duration or 30) *2)),
            (minus_days(date, ((self.duration or 30) * 2) + 1), minus_days(date, (self.duration or 30) * 3)),
            (minus_days(date, ((self.duration or 30) * 3) + 1), minus_days(date, ((self.duration or 30) * 4))),
            (minus_days(date, ((self.duration or 30) * 4) + 1), False),
        ]

        period_table = ('(VALUES %s) AS period_table(date_start, date_stop, period_index)' %
                        ','.join("(%s, %s, %s)" for i, period in enumerate(period_values)))
        params = list(chain.from_iterable(
            (period[0] or None, period[1] or None, i)
            for i, period in enumerate(period_values)
        ))
        return self.env.cr.mogrify(period_table, params).decode(self.env.cr.connection.encoding)

    def get_age_receivable(self):
        date_to = self.end_date

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
                           OR COALESCE(move.invoice_date, account_move_line.date) <= DATE(period_table.date_start)
                       )
                       AND (
                           period_table.date_stop IS NULL
                           OR COALESCE(move.invoice_date, account_move_line.date) >= DATE(period_table.date_stop)
                       )
                       WHERE account.internal_type = %(account_type)s and move.state = 'posted'
                       GROUP BY account_move_line.id, partner.id, trust_property.id, journal.id, move.id, account.id,
                                period_table.period_index, currency_table.rate, currency_table.precision
                       HAVING ROUND(account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0), currency_table.precision) != 0
                       ORDER BY partner_name asc

                   """).format(
            move_line_fields=self._get_move_line_fields('account_move_line'),
            currency_table=self.env['res.currency']._get_query_currency_table(options),
            period_table=self._get_query_period_table(options),
        )
        test = self._get_query_period_table(options)
        params = {
            'account_type': options['filter_account_type'],
            'sign': 1 if options['filter_account_type'] == 'receivable' else -1,
            'date': date_to,
        }
        query = self.env.cr.mogrify(query, params).decode(self.env.cr.connection.encoding)
        # query = self.env['account.aged.receivable'].sudo()._get_sql()
        data = self.env.cr.execute(query)
        data = self.env.cr.fetchall()

        return data

    def get_age_payable(self):
        date_to = self.end_date
        options = self.env['account.aged.payable'].sudo()._get_options(previous_options=None)
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
                           OR COALESCE(move.invoice_date, account_move_line.date) <= DATE(period_table.date_start)
                       )
                       AND (
                           period_table.date_stop IS NULL
                           OR COALESCE(move.invoice_date, account_move_line.date) >= DATE(period_table.date_stop)
                       )
                       WHERE account.internal_type = %(account_type)s and move.state = 'posted'
                       GROUP BY account_move_line.id, partner.id, trust_property.id, journal.id, move.id, account.id,
                                period_table.period_index, currency_table.rate, currency_table.precision
                       HAVING ROUND(account_move_line.balance - COALESCE(SUM(part_debit.amount), 0) + COALESCE(SUM(part_credit.amount), 0), currency_table.precision) != 0
                       ORDER BY partner_name asc

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

        return data

    def print_aged_reports(self):
        self.ensure_one()
        aged_workbook = xlwt.Workbook(encoding='utf-8')
        fp = BytesIO()
        row = 1
        col = -1

        # Content/Text style
        header_content_style = xlwt.easyxf("font: name Arial size 12 px, bold 1, height 170;")
        sub_header_style = xlwt.easyxf("font: name Arial size 10 px, bold 1, height 170; align: horiz center")
        sub_header_content_style = xlwt.easyxf("font: name Arial size 10 px, height 170;")
        line_content_style = xlwt.easyxf("font: name Arial, height 170;")

        if self.report_type == 'receivable':
            data = self.get_age_receivable()
            sheet = aged_workbook.add_sheet('Aged Receivable')
            sheet.write_merge(row, row, 2, 6, "Aged Receivable", header_content_style)
        else:
            data = self.get_age_payable()
            sheet = aged_workbook.add_sheet('Aged Payable')
            sheet.write_merge(row, row, 2, 6, "Aged Payable", header_content_style)

        row +=2

        sheet.write(row, col + 1, "Partner", sub_header_style)
        sheet.write(row, col + 2, "Invoice/Bill", sub_header_style)
        sheet.write(row, col + 3, "Invoice Date", sub_header_style)
        sheet.write(row, col + 4, "Account", sub_header_style)
        sheet.write(row, col + 5, "As on " + str(self.end_date), sub_header_style)
        sheet.write(row, col + 6, "0" + "-" + str(self.duration or 30), sub_header_style)
        sheet.write(row, col + 7, str((self.duration or 30) + 1) + "-" + str((self.duration or 30) * 2), sub_header_style)
        sheet.write(row, col + 8, str(((self.duration or 30) * 2) + 1) + "-" + str((self.duration or 30) * 3), sub_header_style)
        sheet.write(row, col + 9, str(((self.duration or 30) * 3) + 1) + "-" + str((self.duration or 30) * 4), sub_header_style)
        sheet.write(row, col + 10, "Older", sub_header_style)
        sheet.write(row, col + 11, "Total", sub_header_style)

        sheet.col(0).width = 5000
        sheet.col(1).width = 5000
        sheet.col(2).width = 5000
        sheet.col(3).width = 5000
        sheet.col(4).width = 5000
        sheet.col(10).width = 5000

        row +=1
        as_on_total = p1_total = p2_total = p3_total = p4_total = p5_total = row_total = 0
        for rec in data:
            as_on_total += round(rec[-6],2)
            p1_total += round(rec[-5],2)
            p2_total += round(rec[-4],2)
            p3_total += round(rec[-3],2)
            p4_total += round(rec[-2],2)
            p5_total += round(rec[-1],2)
            row_sub_total = (round(rec[-5],2) + round(rec[-4],2) + round(rec[-3],2) + round(rec[-2],2) + round(rec[-1],2))
            row_total += round(row_sub_total,2)

            sheet.write(row, col + 1,rec[14], line_content_style)
            sheet.write(row, col + 2,rec[21], line_content_style)
            sheet.write(row, col + 3,str(rec[9]), line_content_style)
            sheet.write(row, col + 4,str(rec[23]), line_content_style)
            sheet.write(row, col + 5,round(rec[-6],2), line_content_style)
            sheet.write(row, col + 6,round(rec[-5],2), line_content_style)
            sheet.write(row, col + 7,round(rec[-4],2), line_content_style)
            sheet.write(row, col + 8,round(rec[-3],2), line_content_style)
            sheet.write(row, col + 9,round(rec[-2],2), line_content_style)
            sheet.write(row, col + 10,round(rec[-1],2), line_content_style)
            sheet.write(row, col + 11,row_total, sub_header_style)
            row +=1

        row+=1
        sheet.write(row, col + 1, "Total: ", sub_header_style)
        sheet.write(row, col + 2, "", sub_header_style)
        sheet.write(row, col + 3, "", sub_header_style)
        sheet.write(row, col + 4, "", sub_header_style)
        sheet.write(row, col + 5, p1_total, sub_header_style)
        sheet.write(row, col + 6, p1_total, sub_header_style)
        sheet.write(row, col + 7, p2_total, sub_header_style)
        sheet.write(row, col + 8, p3_total, sub_header_style)
        sheet.write(row, col + 9, p4_total, sub_header_style)
        sheet.write(row, col + 10, p5_total, sub_header_style)
        sheet.write(row, col + 11, row_total, sub_header_style)
        aged_workbook.save(fp)

        out = base64.encodebytes(fp.getvalue())

        self.write({'state': 'get', 'report_file': out, 'filename': 'aged_'+self.report_type+'(' + str(self.end_date)+'|'+str(self.duration or 30)+').xls'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'po.ageing.report',
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': self.id,
            'target': 'new',
        }




