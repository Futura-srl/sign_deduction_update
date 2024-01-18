from datetime import datetime, date
from odoo import api, fields, models, http, _, Command
from odoo.exceptions import UserError, ValidationError
import logging


_logger = logging.getLogger(__name__)
date_today = date.today()

class FleetVehicleLogContract(models.Model):
    _inherit = 'fleet.vehicle.log.contract'

    locator_location = fields.Many2one('fleet.renter', domain="[('res_partner_id', '=', insurer_id)]")
    