from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ViolationViolation(models.Model):
    _inherit = "violation.violation"

    is_ztl = fields.Boolean(string="Is ZTL Violation", default=False, help="Indicates whether the violation is related to a ZTL area.")

