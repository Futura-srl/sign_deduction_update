from odoo import fields, models


class FleetVehicleLogServices(models.Model):
    _inherit = 'fleet.vehicle.log.services'
    
    
    def action_view_documents_sign(self):
        # action = self.env.ref('sign.sign_request_action').read()[0]
        # action['domain'] = [('id', 'in', self.sign_request_ids.ids)]
        # return action
        return {
            'name': 'Rifornimenti del veicolo',
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request',
            'view_mode': 'kanban,tree,form',
            'domain': [('anomaly_id', '=', self.id)],
            'target': 'current',
        }
        
    def create_document_request_sign(self):
        template = 35
        self.env['sign.request'].create({
            'anomaly_id': self.id,
            'reference': 'Provolone 3.pdf',
            'request_item_ids': [(0, 0, {
                'partner_id': self.purchaser_id.id,
                'role_id': 4, # Il ruolo 'employee' da errore
        })],
            'template_id': template, # bisogna mettere il template nuovo
        })
        sign_template = self.env['sign.template'].browse(template)  # Recupera il record con ID 13
        sign_template.write({'active': False})