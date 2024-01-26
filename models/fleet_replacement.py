from odoo import fields, models
from datetime import datetime, date
import logging
from odoo import api, fields, models, http, _, Command
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)
date_today = date.today()

class FleetReplacement(models.Model):
    _inherit = 'fleet.replacement'

    replacement_start_date = fields.Datetime(string="Replacement Start Datetime")
    replacement_end_date = fields.Datetime(string="Replacement End Datetime")
