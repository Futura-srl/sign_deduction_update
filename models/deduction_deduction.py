from odoo import models, fields, api


class DeductionDeduction(models.Model):
    _inherit = 'deduction.deduction'
   
    processed = fields.Boolean()