from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AttachFromFleet(models.TransientModel):
    _inherit = 'attach.from.fleet'


    def _domain_tag_id(self):
        default_facet = self.env['documents.facet'].search([('default_facet_for_fleet', '=', True)])
        if default_facet and default_facet.tag_ids:
            return [('id', 'in', default_facet.tag_ids.ids)]
        return []
