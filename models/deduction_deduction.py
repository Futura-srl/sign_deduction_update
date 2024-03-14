from odoo import models, fields, api


class DeductionDeduction(models.Model):
    _inherit = 'deduction.deduction'
    
    processed = fields.Boolean()
    processed_by = fields.Char(readonly=True)
    processed_on = fields.Datetime(readonly=True)
    
    @api.onchange('processed')
    def _deduction_processed(self):
        if self.processed:
            self.processed_by = self.env.user.name
            self.processed_on = fields.Datetime.now()
        else:
            self.processed_by = False
            self.processed_on = False
