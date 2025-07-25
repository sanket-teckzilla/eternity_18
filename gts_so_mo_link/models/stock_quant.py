from psycopg2 import OperationalError, Error

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _update_reserved_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None,
                                  strict=False):
        """ Increase the reserved quantity, i.e. increase `reserved_quantity` for the set of quants
        sharing the combination of `product_id, location_id` if `strict` is set to False or sharing the *exact same characteristics* otherwise.
        This method is called when reserving a move or updating a reserved move line.
        """
        self = self.sudo()
        rounding = product_id.uom_id.rounding
        quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id,
                              strict=strict)
        reserved_quants = []

        if float_compare(quantity, 0, precision_rounding=rounding) > 0:
            # if we want to reserve
            available_quantity = self._get_available_quantity(product_id, location_id, lot_id=lot_id,
                                                              package_id=package_id, owner_id=owner_id, strict=strict)

            if float_compare(quantity, available_quantity, precision_rounding=rounding) > 0:
                # If stock is insufficient, let's raise an error or allow backorders
                raise UserError(_(
                    'You are trying to reserve more products of %s than are available in stock. '
                    'Available stock: %s, Requested: %s') % (product_id.display_name, available_quantity, quantity))

        elif float_compare(quantity, 0, precision_rounding=rounding) < 0:
            # if we want to unreserve
            available_quantity = sum(quants.mapped('reserved_quantity'))
            if float_compare(abs(quantity), available_quantity, precision_rounding=rounding) > 0:
                raise UserError(_(
                    'It is not possible to unreserve more products of %s than are currently reserved.') % product_id.display_name)
        else:
            return reserved_quants

        # Process the reservation or unreservation
        for quant in quants:
            if float_compare(quantity, 0, precision_rounding=rounding) > 0:
                max_quantity_on_quant = quant.quantity - quant.reserved_quantity
                if float_compare(max_quantity_on_quant, 0, precision_rounding=rounding) <= 0:
                    continue
                max_quantity_on_quant = min(max_quantity_on_quant, quantity)
                quant.reserved_quantity += max_quantity_on_quant
                reserved_quants.append((quant, max_quantity_on_quant))
                quantity -= max_quantity_on_quant
                available_quantity -= max_quantity_on_quant
            else:
                max_quantity_on_quant = min(quant.reserved_quantity, abs(quantity))
                quant.reserved_quantity -= max_quantity_on_quant
                reserved_quants.append((quant, -max_quantity_on_quant))
                quantity += max_quantity_on_quant
                available_quantity += max_quantity_on_quant

            # Exit the loop if we have reserved or unreserved the requested quantity
            if float_is_zero(quantity, precision_rounding=rounding) or float_is_zero(available_quantity,
                                                                                     precision_rounding=rounding):
                break

        return reserved_quants

    # def _update_reserved_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None,
    #                               strict=False):
    #     """ Increase the reserved quantity, i.e. increase `reserved_quantity` for the set of quants
    #     sharing the combination of `product_id, location_id` if `strict` is set to False or sharing
    #     the *exact same characteristics* otherwise. Typically, this method is called when reserving
    #     a move or updating a reserved move line. When reserving a chained move, the strict flag
    #     should be enabled (to reserve exactly what was brought). When the move is MTS,it could take
    #     anything from the stock, so we disable the flag. When editing a move line, we naturally
    #     enable the flag, to reflect the reservation according to the edition.
    #
    #     :return: a list of tuples (quant, quantity_reserved) showing on which quant the reservation
    #         was done and how much the system was able to reserve on it
    #     """
    #     self = self.sudo()
    #     rounding = product_id.uom_id.rounding
    #     quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id,
    #                           strict=strict)
    #     reserved_quants = []
    #
    #     if float_compare(quantity, 0, precision_rounding=rounding) > 0:
    #         # if we want to reserve
    #         available_quantity = self._get_available_quantity(product_id, location_id, lot_id=lot_id,
    #                                                           package_id=package_id, owner_id=owner_id, strict=strict)
    #         if float_compare(quantity, available_quantity, precision_rounding=rounding) > 0:
    #             raise UserError(_(
    #                 'It is not possible to reserve more products of %s than you have in stock.') % product_id.display_name)
    #     elif float_compare(quantity, 0, precision_rounding=rounding) < 0:
    #         # if we want to unreserve
    #         available_quantity = sum(quants.mapped('reserved_quantity'))
    #         # if float_compare(abs(quantity), available_quantity, precision_rounding=rounding) > 0:
    #         #     raise UserError(_(
    #         #         'It is not possible to unreserve more products of %s than you have in stock.') % product_id.display_name)
    #     else:
    #         return reserved_quants
    #
    #     for quant in quants:
    #         if float_compare(quantity, 0, precision_rounding=rounding) > 0:
    #             max_quantity_on_quant = quant.quantity - quant.reserved_quantity
    #             if float_compare(max_quantity_on_quant, 0, precision_rounding=rounding) <= 0:
    #                 continue
    #             max_quantity_on_quant = min(max_quantity_on_quant, quantity)
    #             quant.reserved_quantity += max_quantity_on_quant
    #             reserved_quants.append((quant, max_quantity_on_quant))
    #             quantity -= max_quantity_on_quant
    #             available_quantity -= max_quantity_on_quant
    #         else:
    #             max_quantity_on_quant = min(quant.reserved_quantity, abs(quantity))
    #             quant.reserved_quantity -= max_quantity_on_quant
    #             reserved_quants.append((quant, -max_quantity_on_quant))
    #             quantity += max_quantity_on_quant
    #             available_quantity += max_quantity_on_quant
    #
    #         if float_is_zero(quantity, precision_rounding=rounding) or float_is_zero(available_quantity,
    #                                                                                  precision_rounding=rounding):
    #             break
    #     return reserved_quants


class MRPProduction(models.Model):
    _inherit = 'mrp.production'

    show_valuation = fields.Boolean('Valuation', default=False,
                                    help='Show valuation of stock?')
