from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FleetVehicleLogServicesChargedWizard(models.TransientModel):
    _name = 'fleet.vehicle.log.services.charged.wizard'
    _description = 'Fleet Vehicle Log Services Charged Wizard'

    anomaly_id = fields.Many2one('fleet.vehicle.log.services', string='Anomaly', required=True, help="Select the service for which you want to charge the cost.")
    motivation = fields.Text(string='Motivation', required=True, help="Additional information about the services charged.")
    on_pwork = fields.Boolean(string='On Pwork', default=False, help="Check this box if the charged is charged on Pwork.")

    def action_confirm(self):
        # Se confermato salvo il valore nel campo motivation_of_charge del record  nel modello fleet.vehicle.log.services
        active_id = self.anomaly_id
        # Verifico che ci siano record attivi
        if not active_id:
            raise UserError(_("No active records found."))
        # Recupero i record attivi
        services = self.env['fleet.vehicle.log.services'].search([('id', '=', active_id.id)])
        # Verifico che i record siano validi
        if not services:
            raise UserError(_("No valid services found."))
        # Aggiorno il campo motivation_of_charge con il testo inserito
        services.motivation_of_charge = self.motivation
        services.to_be_charged = 'no'
        # Chiudo il wizard
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        # Se annullato non faccio nulla, ma chiudo il wizard
        return {'type': 'ir.actions.act_window_close'}



