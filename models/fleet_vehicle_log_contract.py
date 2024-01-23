from datetime import datetime, date
from odoo import api, fields, models, http, _, Command
from odoo.exceptions import UserError, ValidationError
import logging


_logger = logging.getLogger(__name__)
date_today = date.today()

class FleetVehicleLogContract(models.Model):
    _inherit = 'fleet.vehicle.log.contract'

    locator_location = fields.Many2one('fleet.renter', domain="[('res_partner_id', '=', insurer_id)]")
    is_locator = fields.Boolean(_compute="compute_is_locator")


    @api.depends('vehicle_id')
    def compute_is_locator(self):
        _logger.info(" COMPUTE IS LOCATOR ")
        vehicles = self.env['fleet.vehicle'].search_read([('id', '=', self.vehicle_id['id'])])
        for vehicle in vehicles:
            contracts = self.env['fleet.vehicle.log.contract'].search_read([('vehicle_id', '=', vehicle['id']), ('cost_subtype_id', 'in', [11,46])], order='id desc', limit=1)
            for contract in contracts:
                _logger.info(contract['insurer_id'][0])
                _logger.info(contract['locator_location'][0])
                # controllo se l'id recuperato è presente in fleet.locator
                is_locator = self.env['fleet.renter'].search_read([('res_partner_id', '=', contract['insurer_id'][0]), ('res_city_id.name', '=', contract['locator_location'][1])])
                if is_locator != []:
                    self[0].is_locator = True
                _logger.info(is_locator)
                for record in is_locator:
                    _logger.info(record['email_list'])

            # # recupero il locatore del mezzo
            # locator = self.env['fleet.rent'].search_read([('res_partner_id', '=', record.insurer_id)])
            # if locator != []:
            #     record.is_locator = True
            # else:
            #     record.is_locator = False
            # _logger.info(locator)