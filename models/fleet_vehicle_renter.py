from odoo import fields, models, api, http, _, Command
from datetime import datetime, date
import logging
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)

class FleetRenter(models.Model):
    _name = "fleet.renter"
    _description = "Tabella contentente tutti i locatori di mezzi, le loro sedi e i relativi contatti"

    res_partner_id = fields.Many2one('res.partner', string='Locatore')
    res_city_id = fields.Many2one('res.city', string='Sede')
    email_list = fields.Char()
    name = fields.Char(_compute="_name_location")

    @api.onchange('res_city_id')
    def _name_location(self):
        for record in self:
            record.name = record.res_city_id.name

    
    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            res_city_id = values.get('res_city_id')
            if res_city_id:
                city_name = self.env['res.city'].browse(res_city_id).name
                values['name'] = city_name
        return super(FleetRenter, self).create(values_list)