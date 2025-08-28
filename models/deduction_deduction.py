from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging, requests, json, xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
from datetime import datetime


_logger = logging.getLogger(__name__)


class DeductionDeduction(models.Model):
    _inherit = 'deduction.deduction'
    
    processed = fields.Boolean()
    processed_by = fields.Many2one('res.users', string='Processed By', help="User who processed the deduction.", default=False)
    processed_on = fields.Datetime()
    invoice = fields.Char()
    on_pwork = fields.Boolean(default=False, help="Check this box if the deduction is uploaded to Pwork.")
    response_txt = fields.Text(string='Pwork Response', help="Response from Pwork after processing the deduction.")
    payload = fields.Text(string='Payload', help="The XML payload sent to Pwork.")
    error = fields.Boolean(default=False, help="Indicates if there was an error during processing.")
    is_fleet_rop = fields.Boolean(string="Is Fleet ROP", compute="_compute_is_fleet_rop", help="Indicates if the deduction is related to a fleet ROP service.")


    @api.depends('create_date')
    def _compute_is_fleet_rop(self):
        for record in self:
            # Trova l'utente connesso
            user = self.env.user
            _logger.info(user)
            _logger.info("Verifico se l'utente appartiene ai rop")
            record.is_fleet_rop = user.has_group('Diritti.rop_group')
            _logger.info("Stato del campo is_fleet_rop: %s", record.is_fleet_rop)
            # Ottieni gli identificatori dei gruppi dell'utente connesso
            if 171 in user.groups_id.ids or 117 in user.groups_id.ids:
                record.is_fleet_rop = True
                _logger.info("Utente appartiene al gruppo ROP o al gruppo di gestione dei veicoli")
            else:
                record.is_fleet_rop = False
                _logger.info("Utente non appartiene al gruppo ROP o al gruppo di gestione dei veicoli")
    

    def action_deduction_processed(self):
        for record in self:
            if not record.processed:
                record.processed = True
                record.processed_by = record.env.user.name
                record.processed_on = fields.Datetime.now()
            else:
                record.processed = False
                record.processed_by = False
                record.processed_on = False


    def action_upload_deduction_to_pwork(self):
        for record in self:
            _logger.info(f"Processing deduction id {record.id} for partner {record.employee_id.name}.")
            if not record.on_pwork:
                try:
                    _logger.info(f"Uploading deduction for employee {record.employee_id.name} to Pwork.")
                    # Chiamata alla funzione per l'upload su Pwork
                    payload, response = record.setTM_Voce()
                    record.payload = payload
                    record.response_txt = response
                    if response['ckResponse']['Esito'] == 2:
                        record.on_pwork = True
                        record.error = False
                        _logger.info(f"Deduction for employee {record.employee_id.name} successfully uploaded to Pwork.")
                    else:
                        record.error = True
                except Exception as e:
                    record.error = True
                    record.response_txt = str(e)
                    _logger.error(f"Exception occurred while uploading deduction for employee {record.employee_id.name}: {record.response_txt}")
            else:
                _logger.info(f"Deduction for employee {record.employee_id.name} is already on Pwork, skipping upload.")
                continue




    def _get_access_data(self):
        config_obj = self.env['ir.config_parameter']
        pwork_cod_azienda = config_obj.sudo().get_param('export_hours_to_pwork.pwork_cod_azienda')
        pwork_token = config_obj.sudo().get_param('export_hours_to_pwork.pwork_token')
        return config_obj, pwork_cod_azienda, pwork_token

    def setTM_Voce(self):
        rome_tz = ZoneInfo("Europe/Rome")
        config_obj, pwork_cod_azienda, pwork_token = self._get_access_data()
        _logger.info("Avvio connessione")

        partner_id = self.employee_id
        date = self.date
        # Controlloo se il partner e` un azienda e nel caso salto il record
        if partner_id.is_company:
            return False
        # Controllo se il partner ha dipendenti attivi nella data
        employees = self.env['hr.employee'].search([('address_home_id', '=', partner_id.id), ('active', 'in', [True, False])])
        # Cerco il dipendete con contratti attivi nella data
        if not employees:
            raise UserError(_("No employees found for this partner."))
        for employee in employees:
            contract = self.env['hr.contract'].search([('employee_id', '=', employee.id), ('date_start', '<=', date), '|', ('date_end', '>=', date), ('date_end', '=', False)])
            if contract:
                # Se ho trovato un contratto salvo l'id del dipendente ed esco dal ciclo e procedo con la chiamata
                employee_id = employee.id
                break
        if not contract:
            raise UserError(_("No active contract found for employee {} on date {}.".format(employee.name, date)))



        # Recupero i dati per la chiamata
        employee = self.env['hr.employee'].browse(employee_id)
        pwork_azienda_id = employee.pwork_azienda_id
        pwork_dipendente_id = employee.pwork_dipendente_id
        # trasformo la data in formato dd/mm/yyyy e metto la timezone di Roma
        date = (date.astimezone(rome_tz)).strftime("%d/%m/%Y")
        # Recupero il tipo di voce
        service_id = self.fleet_vehicle_log_service_id.service_type_id.id
        value = self.deduction_value


        if service_id == 80: # Multe
            voce = "ADDCO"
        elif service_id == 81: # Sinistri
            voce = "ADDDA"
        else:
            raise UserError(_("Service type not supported for deduction upload to Pwork."))


        url = 'https://futura.presenze-online.it/webservice/ws.asmx'
        headers = {
            'Content-Type': 'application/soap+xml; charset=utf-8',
        }

        # costruzione del payload della richiesta SOAP XML
        payload = '''<?xml version="1.0" encoding="utf-8"?>
                    <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
                        <soap12:Body>
                            <setTM_Voce xmlns="https://presenze-online.it/">
                                <Token>{}</Token>
                                <CodAzienda>{}</CodAzienda>
                                <Params>
                                    <RequestTMVociEx>
                                        <idDip>{}</idDip>
                                        <idAzienda>{}</idAzienda>
                                        <Data>{}</Data>
                                        <Voce>{}</Voce>
                                        <Value>{}</Value>
                                    </RequestTMVociEx>
                                </Params>
                                <ReturnType>FormatJson</ReturnType>
                            </setTM_Voce>
                        </soap12:Body>
                    </soap12:Envelope>'''.format(pwork_token, pwork_cod_azienda, pwork_dipendente_id, pwork_azienda_id, date, voce, value)

        _logger.info(payload)
        _logger.info("Invio della richiesta HTTP POST")

        # Invio della richiesta HTTP POST
        response = requests.post(url, headers=headers, data=payload)

        _logger.info("Stampa dello stato della risposta HTTP e del contenuto della risposta")

        # stampa dello stato della risposta HTTP e del contenuto della risposta
        _logger.info(response)
        _logger.info(response.status_code)
        _logger.info(response.content)

        # Analisi del documento XML
        xml_string = response.content
        root = ET.fromstring(xml_string)

        # Recupero del valore della stringa JSON
        result = root.find('.//{https://presenze-online.it/}setTM_VoceResult').text.strip()
        data = json.loads(result)
        _logger.info(data)
        return payload, data