from odoo import fields, models, api, http, _, Command
from datetime import datetime, date
import logging
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)

class FleetVehicleLogServices(models.Model):
    _inherit = 'helpdesk.team'

    organization_id = fields.Many2one('res.partner', string='Centro di costo', domain=[('type', '=', 'delivery'), ('is_company', '=', True), ('name', 'ilike', "cdc")])
    