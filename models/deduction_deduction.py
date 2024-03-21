from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class DeductionDeduction(models.Model):
    _inherit = 'deduction.deduction'
    
    processed = fields.Boolean(tracking=True)
    processed_by = fields.Char(tracking=True)
    processed_on = fields.Datetime(tracking=True)
    invoice = fields.Char(tracking=True)
    companies = fields.Char(tracking=True)
    service_type = fields.Char(tracking=True, string="")
    
    @api.onchange('processed')
    def _deduction_processed(self):
        if self.processed:
            self.processed_by = self.env.user.name
            self.processed_on = fields.Datetime.now()
        else:
            self.processed_by = False
            self.processed_on = False


    @api.onchange('employee_id')
    def _employee_active(self):
        # Recupero i dati dell'anomalia (tipo nomalia, data evento)
        _logger.info(self.fleet_vehicle_log_service_id.service_type_id.name)
        _logger.info(self.fleet_vehicle_log_service_id.date)
        _logger.info(self.employee_id.id)
        # fleet_vehicle_log_service = self.env['fleet.vehicle.log.services'].search(self.fleet_vehicle_log_service_id)
        self.service_type = self.fleet_vehicle_log_service_id.service_type_id.name
        
        # Recupero gli employees
        employees = self.env['hr.employee'].search([('address_home_id', '=', self.employee_id.id)])
        _logger.info(employees)        

        employee_list = []
        companies_list = ''
        for i, r in enumerate(employees):
            
            _logger.info(i)
            _logger.info(r.id)
            # Recupero gli employee che avevano il contratto attivo in quel giorno
            contracts_active = self.env['hr.contract'].search([('employee_id', '=', r.id),('date_start', '<=', self.fleet_vehicle_log_service_id.date), '|', ('date_end', '>=', self.fleet_vehicle_log_service_id.date), ('date_end', '=', False)])
            _logger.info(contracts_active)
        for contract_active in contracts_active:
            if r.interinale.name == False:
                companies_list += contract_active.employee_id.company_id.name + ", "
            else:
                companies_list += contract_active.employee_id.interinale.name + ", "
        self.companies = companies_list

        _logger.info(companies_list)
