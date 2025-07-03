import json
from datetime import datetime, timedelta
from babel.dates import format_datetime, format_date
from odoo import models, api, _, fields
from odoo.osv import expression
from odoo.release import version
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.tools.misc import formatLang, format_date as odoo_format_date, get_lang
import random

import ast
class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_json_activity_data(self):
        for journal in self:
            activities = []
            cost_updating_date = self.env.company.invoicing_switch_threshold

            # search activity on move on the journal
            sql_query = '''
                SELECT act.id,
                    act.res_id,
                    act.res_model,
                    act.summary,
                    act_type.name as act_type_name,
                    act_type.name as act_type_name,
                    act_type.category as activity_category,
                    act.date_deadline,
                    m.date,
                    m.ref,
                    CASE WHEN act.date_deadline < CURRENT_DATE THEN 'late' ELSE 'future' END as status
                FROM account_move m
                    LEFT JOIN mail_activity act ON act.res_id = m.id
                    LEFT JOIN mail_activity_type act_type ON act.activity_type_id = act_type.id
                WHERE act.res_model = 'account.move'
                    AND m.journal_id = %s AND m.invoice_date >= \'''' + cost_updating_date.strftime(DF) + '''\'
            '''
            self.env.cr.execute(sql_query, (journal.id,))
            for activity in self.env.cr.dictfetchall():
                act = {
                    'id': activity.get('id'),
                    'res_id': activity.get('res_id'),
                    'res_model': activity.get('res_model'),
                    'status': activity.get('status'),
                    'name': (activity.get('summary') or activity.get('act_type_name')),
                    'activity_category': activity.get('activity_category'),
                    'date': odoo_format_date(self.env, activity.get('date_deadline'))
                }
                if activity.get('activity_category') == 'tax_report' and activity.get('res_model') == 'account.move':
                    act['name'] = activity.get('ref')

                activities.append(act)
            journal.json_activity_data = json.dumps({'activities': activities})

    def get_line_graph_datas(self):
        """Computes the data used to display the graph for bank and cash journals in the accounting dashboard"""
        currency = self.currency_id or self.company_id.currency_id
        cost_updating_date = self.env.company.invoicing_switch_threshold
        date_format = "%Y-%M-%D"

        def build_graph_data(date, amount):
            # display date in locale format
            name = format_date(date, 'd LLLL Y', locale=locale)
            short_name = format_date(date, 'd MMM', locale=locale)
            return {'x': short_name, 'y': amount, 'name': name}

        self.ensure_one()
        BankStatement = self.env['account.bank.statement']
        data = []
        today = datetime.today()
        last_month = today + timedelta(days=-30)
        locale = get_lang(self.env).code

        # starting point of the graph is the last statement
        last_stmt = self._get_last_bank_statement(
            domain=[('move_id.state', '=', 'posted'), ('move_id.invoice_date', '>=', cost_updating_date.strftime(DF))])

        last_balance = last_stmt and last_stmt.balance_end_real or 0
        data.append(build_graph_data(today, last_balance))

        # then we subtract the total amount of bank statement lines per day to get the previous points
        # (graph is drawn backward)
        date = today
        amount = last_balance

        query = '''
            SELECT move.date, sum(st_line.amount) as amount
            FROM account_bank_statement_line st_line
            JOIN account_move move ON move.id = st_line.move_id
            WHERE move.journal_id = %s
            AND move.date > %s
            AND move.date <= %s AND move.invoice_date >=\'''' + cost_updating_date.strftime(DF) + '''\'
            GROUP BY move.date
            ORDER BY move.date desc
        '''
        self.env.cr.execute(query, (self.id, last_month, today))
        query_result = self.env.cr.dictfetchall()
        for val in query_result:
            date = val['date']
            if date != today.strftime(DF):  # make sure the last point in the graph is today
                data[:0] = [build_graph_data(date, amount)]
            amount = currency.round(amount - val['amount'])

        # make sure the graph starts 1 month ago
        if date.strftime(DF) != last_month.strftime(DF):
            data[:0] = [build_graph_data(last_month, amount)]

        [graph_title, graph_key] = self._graph_title_and_key()
        color = '#875A7B' if 'e' in version else '#7c7bad'

        is_sample_data = not last_stmt and len(query_result) == 0
        if is_sample_data:
            data = []
            for i in range(30, 0, -5):
                current_date = today + timedelta(days=-i)
                data.append(build_graph_data(current_date, random.randint(-5, 15)))

        return [{'values': data, 'title': graph_title, 'key': graph_key, 'area': True, 'color': color,
                 'is_sample_data': is_sample_data}]

    def get_bar_graph_datas(self):
        data = []
        today = fields.Datetime.now(self)
        data.append({'label': _('Due'), 'value': 0.0, 'type': 'past'})
        day_of_week = int(format_datetime(today, 'e', locale=get_lang(self.env).code))
        first_day_of_week = today + timedelta(days=-day_of_week + 1)
        for i in range(-1, 4):
            if i == 0:
                label = _('This Week')
            elif i == 3:
                label = _('Not Due')
            else:
                start_week = first_day_of_week + timedelta(days=i * 7)
                end_week = start_week + timedelta(days=6)
                if start_week.month == end_week.month:
                    label = str(start_week.day) + '-' + str(end_week.day) + ' ' + format_date(end_week, 'MMM',
                                                                                              locale=get_lang(
                                                                                                  self.env).code)
                else:
                    label = format_date(start_week, 'd MMM', locale=get_lang(self.env).code) + '-' + format_date(
                        end_week, 'd MMM', locale=get_lang(self.env).code)
            data.append({'label': label, 'value': 0.0, 'type': 'past' if i < 0 else 'future'})

        # Build SQL query to find amount aggregated by week
        (select_sql_clause, query_args) = self._get_bar_graph_select_query()
        query = ''
        start_date = (first_day_of_week + timedelta(days=-7))
        for i in range(0, 6):
            if i == 0:
                query += "(" + select_sql_clause + " and invoice_date_due < '" + start_date.strftime(DF) + "')"
            elif i == 5:
                query += " UNION ALL (" + select_sql_clause + " and invoice_date_due >= '" + start_date.strftime(
                    DF) + "')"
            else:
                next_date = start_date + timedelta(days=7)
                query += " UNION ALL (" + select_sql_clause + " and invoice_date_due >= '" + start_date.strftime(
                    DF) + "' and invoice_date_due < '" + next_date.strftime(DF) + "')"
                start_date = next_date

        self.env.cr.execute(query, query_args)
        query_results = self.env.cr.dictfetchall()
        is_sample_data = True
        for index in range(0, len(query_results)):
            if query_results[index].get('aggr_date') != None:
                is_sample_data = False
                data[index]['value'] = query_results[index].get('total')

        [graph_title, graph_key] = self._graph_title_and_key()

        if is_sample_data:
            for index in range(0, len(query_results)):
                data[index]['type'] = 'o_sample_data'
                # we use unrealistic values for the sample data
                data[index]['value'] = random.randint(0, 20)
                graph_key = _('Sample data')

        return [{'values': data, 'title': graph_title, 'key': graph_key, 'is_sample_data': is_sample_data}]

    def _get_bar_graph_select_query(self):
        """
        Returns a tuple containing the base SELECT SQL query used to gather
        the bar graph's data as its first element, and the arguments dictionary
        for it as its second.
        """
        sign = '' if self.type == 'sale' else '-'
        cost_updating_date = self.env.company.invoicing_switch_threshold
        date_format = "%Y-%M-%D"

        return ('''
            SELECT
                ''' + sign + ''' + SUM(move.amount_residual_signed) AS total,
                MIN(invoice_date_due) AS aggr_date
            FROM account_move move
            WHERE move.journal_id = %(journal_id)s
            AND move.state = 'posted'
            AND move.payment_state in ('not_paid', 'partial')
            AND move.move_type IN %(invoice_types)s AND move.invoice_date >=\'''' + cost_updating_date.strftime(DF) + '''\'
        ''', {
            'invoice_types': tuple(self.env['account.move'].get_invoice_types(True)),
            'journal_id': self.id
        })

    def get_journal_dashboard_datas(self):
        currency = self.currency_id or self.company_id.currency_id
        cost_updating_date = self.env.company.invoicing_switch_threshold
        number_to_reconcile = number_to_check = last_balance = 0
        has_at_least_one_statement = False
        bank_account_balance = nb_lines_bank_account_balance = 0
        outstanding_pay_account_balance = nb_lines_outstanding_pay_account_balance = 0
        title = ''
        number_draft = number_waiting = number_late = to_check_balance = 0
        sum_draft = sum_waiting = sum_late = 0.0
        if self.type in ('bank', 'cash'):
            last_statement = self._get_last_bank_statement(
                domain=[('move_id.state', '=', 'posted'),
                        ('move_id.invoice_date', '>=', cost_updating_date.strftime(DF))])
            last_balance = last_statement.balance_end
            has_at_least_one_statement = bool(last_statement)
            bank_account_balance, nb_lines_bank_account_balance = self._get_journal_bank_account_balance(
                domain=[('move_id.state', '=', 'posted'),
                        ('move_id.invoice_date', '>=', cost_updating_date.strftime(DF))])
            outstanding_pay_account_balance, nb_lines_outstanding_pay_account_balance = self._get_journal_outstanding_payments_account_balance(
                domain=[('move_id.state', '=', 'posted'),
                        ('move_id.invoice_date', '>=', cost_updating_date.strftime(DF))])

            self._cr.execute('''
                SELECT COUNT(st_line.id)
                FROM account_bank_statement_line st_line
                JOIN account_move st_line_move ON st_line_move.id = st_line.move_id
                JOIN account_bank_statement st ON st_line.statement_id = st.id
                WHERE st_line_move.journal_id IN %s
                AND st.state = 'posted'
                AND NOT st_line.is_reconciled AND st_line_move.invoice_date >=\'''' + cost_updating_date.strftime(DF) + '''\'
            ''', [tuple(self.ids)])
            number_to_reconcile = self.env.cr.fetchone()[0]

            to_check_ids = self.to_check_ids()
            number_to_check = len(to_check_ids)
            to_check_balance = sum([r.amount for r in to_check_ids])
        # TODO need to check if all invoices are in the same currency than the journal!!!!
        elif self.type in ['sale', 'purchase']:
            title = _('Bills to pay') if self.type == 'purchase' else _('Invoices owed to you')
            self.env['account.move'].flush(
                ['amount_residual', 'currency_id', 'move_type', 'invoice_date', 'company_id', 'journal_id', 'date',
                 'state', 'payment_state'])

            (query, query_args) = self._get_open_bills_to_pay_query()
            self.env.cr.execute(query, query_args)
            query_results_to_pay = self.env.cr.dictfetchall()

            (query, query_args) = self._get_draft_bills_query()
            self.env.cr.execute(query, query_args)
            query_results_drafts = self.env.cr.dictfetchall()

            today = fields.Date.context_today(self)
            query = '''
                SELECT
                    (CASE WHEN move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * amount_residual AS amount_total,
                    currency_id AS currency,
                    move_type,
                    invoice_date,
                    company_id
                FROM account_move move
                WHERE journal_id = %s
                AND date <= %s
                AND state = 'posted'
                AND payment_state in ('not_paid', 'partial')
                AND move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt') AND move.invoice_date >=\'''' + cost_updating_date.strftime(
                DF) + '''\';
            '''
            self.env.cr.execute(query, (self.id, today))
            late_query_results = self.env.cr.dictfetchall()
            curr_cache = {}
            (number_waiting, sum_waiting) = self._count_results_and_sum_amounts(query_results_to_pay, currency,
                                                                                curr_cache=curr_cache)
            (number_draft, sum_draft) = self._count_results_and_sum_amounts(query_results_drafts, currency,
                                                                            curr_cache=curr_cache)
            (number_late, sum_late) = self._count_results_and_sum_amounts(late_query_results, currency,
                                                                          curr_cache=curr_cache)
            read = self.env['account.move'].read_group(
                [('journal_id', '=', self.id), ('invoice_date', '>=', cost_updating_date.strftime(DF)),
                 ('to_check', '=', True)], ['amount_total'], 'journal_id', lazy=False)
            if read:
                number_to_check = read[0]['__count']
                to_check_balance = read[0]['amount_total']
        elif self.type == 'general':
            read = self.env['account.move'].read_group(
                [('journal_id', '=', self.id), ('invoice_date', '>=', cost_updating_date.strftime(DF)),
                 ('to_check', '=', True)], ['amount_total'], 'journal_id', lazy=False)
            if read:
                number_to_check = read[0]['__count']
                to_check_balance = read[0]['amount_total']

        is_sample_data = self.kanban_dashboard_graph and any(
            data.get('is_sample_data', False) for data in json.loads(self.kanban_dashboard_graph))

        return {
            'number_to_check': number_to_check,
            'to_check_balance': formatLang(self.env, to_check_balance, currency_obj=currency),
            'number_to_reconcile': number_to_reconcile,
            'account_balance': formatLang(self.env, currency.round(bank_account_balance), currency_obj=currency),
            'has_at_least_one_statement': has_at_least_one_statement,
            'nb_lines_bank_account_balance': nb_lines_bank_account_balance,
            'outstanding_pay_account_balance': formatLang(self.env, currency.round(outstanding_pay_account_balance),
                                                          currency_obj=currency),
            'nb_lines_outstanding_pay_account_balance': nb_lines_outstanding_pay_account_balance,
            'last_balance': formatLang(self.env, currency.round(last_balance) + 0.0, currency_obj=currency),
            'number_draft': number_draft,
            'number_waiting': number_waiting,
            'number_late': number_late,
            'sum_draft': formatLang(self.env, currency.round(sum_draft) + 0.0, currency_obj=currency),
            'sum_waiting': formatLang(self.env, currency.round(sum_waiting) + 0.0, currency_obj=currency),
            'sum_late': formatLang(self.env, currency.round(sum_late) + 0.0, currency_obj=currency),
            'currency_id': currency.id,
            'bank_statements_source': self.bank_statements_source,
            'title': title,
            'is_sample_data': is_sample_data,
            'company_count': len(self.env.companies)
        }

    def _get_open_bills_to_pay_query(self):
        """
        Returns a tuple containing the SQL query used to gather the open bills
        data as its first element, and the arguments dictionary to use to run
        it as its second.
        """
        cost_updating_date = self.env.company.invoicing_switch_threshold

        return ('''
            SELECT
                (CASE WHEN move.move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * move.amount_residual AS amount_total,
                move.currency_id AS currency,
                move.move_type,
                move.invoice_date,
                move.company_id
            FROM account_move move
            WHERE move.journal_id = %(journal_id)s
            AND move.state = 'posted'
            AND move.payment_state in ('not_paid', 'partial')
            AND move.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt') AND move.invoice_date >=\'''' + cost_updating_date.strftime(
            DF) + '''\';
        ''', {'journal_id': self.id})

    def _get_draft_bills_query(self):
        """
        Returns a tuple containing as its first element the SQL query used to
        gather the bills in draft state data, and the arguments
        dictionary to use to run it as its second.
        """
        cost_updating_date = self.env.company.invoicing_switch_threshold
        date_format = "%Y-%M-%D"

        return ('''
            SELECT
                (CASE WHEN move.move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * move.amount_total AS amount_total,
                move.currency_id AS currency,
                move.move_type,
                move.invoice_date,
                move.company_id
            FROM account_move move
            WHERE move.journal_id = %(journal_id)s
            AND move.state = 'draft'
            AND move.payment_state in ('not_paid', 'partial')
            AND move.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt') AND move.invoice_date >=\'''' + cost_updating_date.strftime(
            DF) + '''\';
        ''', {'journal_id': self.id})

    def _count_results_and_sum_amounts(self, results_dict, target_currency, curr_cache=None):
        """ Loops on a query result to count the total number of invoices and sum
        their amount_total field (expressed in the given target currency).
        amount_total must be signed !
        """
        rslt_count = 0
        rslt_sum = 0.0
        # Create a cache with currency rates to avoid unnecessary SQL requests. Do not copy
        # curr_cache on purpose, so the dictionary is modified and can be re-used for subsequent
        # calls of the method.
        curr_cache = {} if curr_cache is None else curr_cache
        cost_updating_date = self.env.company.invoicing_switch_threshold
        for result in results_dict:
            inv_date = result.get('invoice_date')
            if inv_date.strftime(DF) >= cost_updating_date.strftime(DF):
                cur = self.env['res.currency'].browse(result.get('currency'))
                company = self.env['res.company'].browse(result.get('company_id')) or self.env.company
                rslt_count += 1
                date = result.get('invoice_date') or fields.Date.context_today(self)

                amount = result.get('amount_total', 0) or 0
                if cur != target_currency:
                    key = (cur, target_currency, company, date)
                    # Using setdefault will call _get_conversion_rate, so we explicitly check the
                    # existence of the key in the cache instead.
                    if key not in curr_cache:
                        curr_cache[key] = self.env['res.currency']._get_conversion_rate(*key)
                    amount *= curr_cache[key]
                rslt_sum += target_currency.round(amount)
        return (rslt_count, rslt_sum)

    def action_create_new(self):
        ctx = self._context.copy()
        ctx['default_journal_id'] = self.id
        if self.type == 'sale':
            ctx['default_move_type'] = 'out_refund' if ctx.get('refund') else 'out_invoice'
        elif self.type == 'purchase':
            ctx['default_move_type'] = 'in_refund' if ctx.get('refund') else 'in_invoice'
        else:
            ctx['default_move_type'] = 'entry'
            ctx['view_no_maturity'] = True
        return {
            'name': _('Create invoice/bill'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'view_id': self.env.ref('account.view_move_form').id,
            'context': ctx,
        }

    def create_cash_statement(self):
        ctx = self._context.copy()
        ctx.update({'journal_id': self.id, 'default_journal_id': self.id, 'default_journal_type': 'cash'})
        open_statements = self.env['account.bank.statement'].search(
            [('journal_id', '=', self.id), ('state', '=', 'open')])
        action = {
            'name': _('Create cash statement'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.bank.statement',
            'context': ctx,
        }
        if len(open_statements) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': open_statements.id,
            })
        elif len(open_statements) > 1:
            action.update({
                'view_mode': 'list,form',
                'domain': [('id', 'in', open_statements.ids)],
            })
        return action

    def to_check_ids(self):
        self.ensure_one()
        domain = self.env['account.move.line']._get_suspense_moves_domain()
        cost_updating_date = self.env.company.invoicing_switch_threshold
        domain += [('journal_id', '=', self.id), ('statement_line_id.is_reconciled', '=', False)]
        domain += [('move_id.invoice_date', '>=', cost_updating_date), ('statement_line_id.is_reconciled', '=', False)]
        statement_line_ids = self.env['account.move.line'].search(domain).mapped('statement_line_id')
        return statement_line_ids


    def open_action(self):
        """return action based on type for related journals"""
        self.ensure_one()
        action_name = self._select_action_to_open()
        cost_updating_date = self.env.company.invoicing_switch_threshold

        # Set 'account.' prefix if missing.
        if not action_name.startswith("account."):
            action_name = 'account.%s' % action_name

        action = self.env["ir.actions.act_window"]._for_xml_id(action_name)

        context = self._context.copy()
        if 'context' in action and type(action['context']) == str:
            context.update(ast.literal_eval(action['context']))
        else:
            context.update(action.get('context', {}))
        action['context'] = context
        action['context'].update({
            'default_journal_id': self.id,
            'search_default_journal_id': self.id,
        })

        domain_type_field = action['res_model'] == 'account.move.line' and 'move_id.move_type' or 'move_type'  # The model can be either account.move or account.move.line
        domain_date_field = action['res_model'] == 'account.move.line' and 'move_id.invoice_date' or 'invoice_date'  # The model can be either account.move or account.move.line

        # Override the domain only if the action was not explicitly specified in order to keep the
        # original action domain.
        if not self._context.get('action_name'):
            if self.type == 'sale':
                action['domain'] = [(domain_type_field, 'in', ('out_invoice', 'out_refund', 'out_receipt')),(domain_date_field, '>=', cost_updating_date)]
            elif self.type == 'purchase':
                action['domain'] = [(domain_type_field, 'in', ('in_invoice', 'in_refund', 'in_receipt')),(domain_date_field, '>=', cost_updating_date)]

        return action