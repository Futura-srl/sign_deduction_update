from odoo import fields, models
from docx import Document
from docx2pdf import convert
from datetime import datetime, date
import subprocess
import pdfkit
import tempfile
import logging
import base64
import re
import os
from pydocx import PyDocX
from docx.shared import Pt
from shutil import copyfileobj
from odoo import api, fields, models, http, _, Command
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)
date_today = date.today()

class FleetVehicleLogServices(models.Model):
    _inherit = 'fleet.vehicle.log.services'

    state = fields.Selection([('new', 'Inserito'), ('reported', 'Segnalato'), ('running', 'Processato'), ('done', 'Completato'), ('cancelled', 'Annullato')], readonly=True, track_visibility='onchange')
    groups_ids = fields.Char(string='Groups of the User', compute='_compute_groups_admin', store=False)
    is_admin = fields.Boolean(compute='_compute_groups_admin', store=False)
    is_fleet_admin = fields.Boolean(compute='_compute_groups_fleet_admin', store=False)


    @api.model_create_multi
    def create(self, vals_list):
        res = super(FleetVehicleLogServices, self).create(vals_list)
        if res['service_type_id'].id == 9:
            self.create_reminder(vals_list, res)
        return res

    
    @api.depends('is_admin')
    def _compute_groups_admin(self):
        for record in self:
            # Trova l'utente connesso
            user = self.env.user
            # Ottieni gli identificatori dei gruppi dell'utente connesso
            if 4 in user.groups_id.ids:
                record.is_admin = True
            else:
                record.is_admin = False
                
    @api.depends('is_fleet_admin')
    def _compute_groups_fleet_admin(self):
        for record in self:
            # Trova l'utente connesso
            user = self.env.user
            # Ottieni gli identificatori dei gruppi dell'utente connesso
            if 17 in user.groups_id.ids:
                record.is_fleet_admin = True
            else:
                record.is_fleet_admin = False


    
   #################### 
   #################### 
   #     MULTE        #
   #################### 
   #################### 

    
    def action_view_documents_sign(self):
        # action = self.env.ref('sign.sign_request_action').read()[0]
        # action['domain'] = [('id', 'in', self.sign_request_ids.ids)]
        # return action
        return {
            'name': 'Documenti con firma richiesta',
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request',
            'view_mode': 'kanban,tree,form',
            'domain': [('anomaly_id', '=', self.id)],
            'target': 'current',
        }

    def create_pdf_for_sign(self):
        if self.deduction_point == 0:
            doc_base64 = self.env['ir.attachment'].browse(163362) # Template da 1 pagina
        else:
            doc_base64 = self.env['ir.attachment'].browse(163364) # Template da 2 pagine
        doc_base64_content = doc_base64.datas.decode('utf-8')
        decoded_bytes = base64.b64decode(doc_base64_content)
    
        with tempfile.NamedTemporaryFile(suffix='_original.docx', delete=False) as temp_file:
            temp_file.write(decoded_bytes)
            temp_file_path = temp_file.name
    
        doc = Document(temp_file_path)
        deduction_ids = self.deduction_ids.ids
        total_import = 0.0
        # Stampare gli ID singolarmente
        for deduction_id in deduction_ids:
            _logger.info("Stampo singolo record")
            _logger.info(str(deduction_id))
            _logger.info(self.env['deduction.deduction'].search([('id', '=', deduction_id), ('date', '!=', False)]).deduction_value)
            total_import += self.env['deduction.deduction'].search([('id', '=', deduction_id), ('date', '!=', False)]).deduction_value
        _logger.info("importo totale %s", total_import)
        importo_formattato = "{:.2f}".format(total_import).replace(".", ",")
        _logger.info("STAMPO I VALORI")

        
        
        
        if self.company_id.name == "Logistica S.R.L.":
            azienda = "Futura Logistica S.r.l."
        else:
            azienda = self.company_id.name
        replacements = {
            "[NOME]": self.purchaser_id.name,
            "[AZIENDA]": azienda,
            "[DATA]": date_today.strftime('%d/%m/%Y'),
            "[DATA_EVENTO]": str(self.date.date().strftime('%d/%m/%Y')),
            "[LUOGO]": self.city_id.name,
            "[TARGA]": self.vehicle_id.license_plate,
            "[IMPORTO]": str(importo_formattato),
            "[NUMERO_VERBALE]": self.description + " del " + str(self.date.date().strftime('%d/%m/%Y')),
            "[NUMERO_PROTOCOLLO]": str(self.id),
        }
    
        for paragraph in doc.paragraphs:
            for key, value in replacements.items():
                if key in paragraph.text:
                    for run in paragraph.runs:
                        run.text = run.text.replace(key, value)
    
        doc.save(temp_file_path)


        # Ottenere il percorso senza l'estensione
        file_base_name = os.path.splitext(temp_file_path)[0]
        
        # Specifica il percorso del file PDF risultante
        file_output_pdf = file_base_name + ".pdf"

        
        # Comando per la conversione utilizzando LibreOffice
        command = ['libreoffice', '--headless', '--convert-to', 'pdf', temp_file_path, '--outdir', "/tmp"]
        
        # Esegui il comando
        subprocess.run(command)
        _logger.info("STAMPOOOOOO")
        _logger.info(str(file_output_pdf))

        # Leggi il contenuto del file PDF
        with open(file_output_pdf, "rb") as pdf_file:
            pdf_content = pdf_file.read()
        
        # Converti il contenuto del PDF in base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        return pdf_base64
            
    def upload_attachment(self):
        data = self.create_pdf_for_sign()
        reference_name = str(self.id) + "_" + str(self.service_type_id.name) + "_" + str(self.description) + ".pdf"
        attachment = self.env['ir.attachment'].create({
            'company_id': self.company_id.id,
            'name': reference_name,
            'res_id': "",
            'res_model': "sign.template",
            'type': "binary",
            'datas': data,
            'document_ids': [(0, 0, {
                'folder_id': "4"
            })]
        })
        return attachment.id

    def add_template_for_sign(self):
        attachment_id = self.upload_attachment()
        template_values = {
            'attachment_id': attachment_id,
            'sign_item_ids': [
                (0, 0, {
                    'type_id': 11,
                    'required': True,
                    'responsible_id': 3,
                    'page': 1,
                    'posX': 0.523,
                    'posY': 0.695,
                    'width': 0.108,
                    'height': 0.015,
                }),
                (0, 0, {
                    'type_id': 7,
                    'required': True,
                    'responsible_id': 3,
                    'page': 1,
                    'posX': 0.691,
                    'posY': 0.697,
                    'width': 0.150,
                    'height': 0.015,
                }),
                (0, 0, {
                    'type_id': 1,
                    'required': True,
                    'responsible_id': 3,
                    'page': 1,
                    'posX': 0.503,
                    'posY': 0.723,
                    'width': 0.307,
                    'height': 0.052,
                }),
            ],
        }
        
        if self.deduction_point != 0:
            template_values['sign_item_ids'].extend([
                (0, 0, {
                    'type_id': 11,
                    'required': True,
                    'responsible_id': 3,
                    'page': 2,
                    'posX': 0.524,
                    'posY': 0.524,
                    'width': 0.103,
                    'height': 0.014,
                }),
                (0, 0, {
                    'type_id': 7,
                    'required': True,
                    'responsible_id': 3,
                    'page': 2,
                    'posX': 0.685,
                    'posY': 0.524,
                    'width': 0.103,
                    'height': 0.015,
                }),
                (0, 0, {
                    'type_id': 1,
                    'required': True,
                    'responsible_id': 3,
                    'page': 2,
                    'posX': 0.498,
                    'posY': 0.541,
                    'width': 0.330,
                    'height': 0.049,
                }),
            ])
        
        template = self.env['sign.template'].create(template_values)
        _logger.info(template.id)
        return template.id

    def send_attachment_with_email(self, attachment_id):
        # Controllo se è interinale
        is_interinal = self.env['hr.employee'].search_read([('address_home_id', '=', self.purchaser_id.id), ('active', '=', True)])
        email = self.env['res.partner'].search_read([('id', '=', self.purchaser_id.id)], ['email_personale'])[0]['email_personale']
        _logger.info(f"La mail va inviata a {email}")

        deduction_ids = self.deduction_ids.ids
        total_import = 0.0
        for deduction_id in deduction_ids:
            total_import += self.env['deduction.deduction'].search([('id', '=', deduction_id), ('date', '!=', False)]).deduction_value
        _logger.info("importo totale %s", total_import)
        importo_formattato = "{:.2f}".format(total_import).replace(".", ",")
        if self.deduction_point > 0:
            body_interinale = f"""<p>Buongiorno,</br>in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di competenza della risorsa {self.purchaser_id.name} in quanto al momento della violazione avvenuta in data/ore (data Evento) si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione comporta la decurtazione di punti {self.deduction_point}.</p>
<p><b>Qualora la contravvenzione comporti la decurtazione di Punti vi chiediamo entro 5 giorni di rispondere allegando alla presente:</b>
<ul>
    <li>Copia fronte e retro della patente sulla stessa facciata con scritto di proprio pugno dall’autista la seguente frase 'Io sottoscritto {self.purchaser_id.name} nato a (paese e provincia di nascita) residente a (paese e provincia di residenza) in via (via) dichiaro che la copia del presente documento (indicare tipo documento) n° (numero documento) è conforme all'originale in mio possesso. (data e firma leggibile)'.</li>
    <li>Modulo comunicazione dati conducente allegata al presente verbale correttamente compilato e firmato.</li>
</ul></p>
<p><b>Vi chiedo di procedere al rilascio della vostra contestazione ed operare la relativa trattenuta dell’importo {importo_formattato}</b> in base a quanto vi verrà quantificato nel Timesheet come di consueto, da sommarsi qualora la contravvenzione preveda la decurtazione di punti e la risorsa non intenda comunicare i propri dati ulteriori 220,00€ a fronte della sanzione che riceveremo per la mancata comunicazione dei dati del conducente all’ente accertatore.</p>
<p>Vi informiamo che è stata inoltrata la contestazione dell’evento da firmare per presa visione alla risorsa all’indirizzo (indirizzo mail dipendente).</p>
<p>Per eventuali contestazioni vi chiediamo di rispondere sempre a questa mail.</p>
</br></br>
<p>Futura</p>"""

            body_employee = f'''<p>Buongiorno,</br>in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di Vostra competenza in quanto al momento della violazione avvenuta in data/ore {self.date} si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione comporta la decurtazione di punti {self.deduction_point}.</p>
<p><b>Qualora la contravvenzione comporti la decurtazione di Punti vi chiediamo entro 5 giorni di rispondere allegando alla presente:</b>
<ul>
    <li>Copia fronte e retro della patente sulla stessa facciata con scritto di proprio pugno dall’autista la seguente frase 'Io sottoscritto {self.purchaser_id.name} nato a (paese e provincia di nascita) residente a (paese e provincia di residenza) in via (via) dichiaro che la copia del presente documento (indicare tipo documento) n° (numero documento) è conforme all'originale in mio possesso. (data e firma leggibile)'.</li>
    <li>Modulo comunicazione dati conducente allegata al presente verbale correttamente compilato e firmato.</li>
</ul></p>
<p>Al presente verbale saranno da sommarsi qualora la contravvenzione preveda la decurtazione di punti e Lei non intenda comunicare i propri dati ulteriori 220,00€ a fronte della sanzione che riceveremo per la mancata comunicazione dei dati del conducente all’ente accertatore.</p>
<p>Riceverà ulteriore mail con un link che riporterà alla contestazione da firmare per presa visione, tale firma non esclude l’eventuale addebito</p>
<p>Per eventuali contestazioni vi chiediamo di far riferimento al vostro responsabile di sede.</p>
</br></br>
<p>Futura</p>'''
        else:
            body_employee = f"""<p>Buongiorno,</br>in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di Vostra competenza in quanto al momento della violazione avvenuta in data/ore {self.date} si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione non comporta la decurtazione di punti.</p>
<p>Riceverà ulteriore mail con un link che riporterà alla contestazione da firmare per presa visione, tale firma non esclude l’eventuale addebito</p>
<p>Per eventuali contestazioni vi chiediamo di far riferimento al vostro responsabile di sede.</p>
</br>
<p>Futura</p>"""
            body_interinale = f"""<p>Buongiorno,</br>in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di competenza della risorsa {self.purchaser_id.name} in quanto al momento della violazione avvenuta in data/ore {self.date} si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione non comporta la decurtazione di punti.</p>
<p><b>Vi chiedo di procedere al rilascio della vostra contestazione ed operare la relativa trattenuta dell’importo {importo_formattato}</b> in base a quanto vi verrà quantificato nel Timesheet come di consueto.</p>
<p>Vi informiamo che è stata inoltrata la contestazione dell’evento da firmare per presa visione alla risorsa all’indirizzo (indirizzo mail dipendente).</p>
<p>Per eventuali contestazioni vi chiediamo di rispondere sempre a questa mail.</p>
</br>
<p>Futura</p>"""
            
        # Invia l'email con l'allegato al dipendente
        mail_values = {
            'subject': f'Contravvenzione ns. rif. {str(self.id)} - Verbale n°  {self.description}  - {self.purchaser_id.name}',
            'email_from': 'noreply@futurasl.com',
            'email_to': email,
            'email_cc': 'catchall@futurasl-stage.odoo.com',
            'model': 'fleet.vehicle.log.services',
            'res_id': self.id,
            'body_html': body_employee,
            'attachment_ids': [(4, attachment_id)],  # Aggiungi l'allegato all'email
        }

        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()
        partner_id = self.env['res.users'].browse(self.env.uid).partner_id.id
        self.env['mail.message'].create({'model': 'fleet.vehicle.log.services','res_id': self.id,'author_id': partner_id,'message_type': 'comment','body': "<p>Ho appena inviato le seguenti email al dipendente:</p><p>Comunicazione da far firmare al dipendente</p><p>Copia del verbale</p>"})

        ###########################
        ###########################
        ###########################
        ###########################
        # Invia l'email con l'allegato all'interinale
        # DA FINIRE DI GESTIRE LA PARTE DELL'INVIO ALL'INTERINALE. 
        email_interinale = self.check_interinale_a()
        if email_interinale != False:
            mail_values = {
                'subject': f'Contravvenzione ns. rif. {str(self.id)} - Verbale n°  {self.description}  - {self.purchaser_id.name}',
                'email_from': 'noreply@futurasl.com',
                'email_to': email_interinale,
                'email_cc': 'catchall@futurasl-stage.odoo.com',
                'model': 'fleet.vehicle.log.services',
                'res_id': self.id,
                'body_html': body_interinale,
                'attachment_ids': [(4, attachment_id)],  # Aggiungi l'allegato all'email
            }
    
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            partner_id = self.env['res.users'].browse(self.env.uid).partner_id.id
            self.env['mail.message'].create({'model': 'fleet.vehicle.log.services','res_id': self.id,'author_id': partner_id,'body': "<p>Ho appena inviato la seguente mail all'interinale:</p><p>Copia del verbale</p>"})


    
            
    def create_document_request_sign(self):
        self.check_data()
        template_id = self.add_template_for_sign()
        _logger.info(template_id)
        reference_name = str(self.id) + " " + str(self.service_type_id.name) + " " + str(self.description)
        sign_request = self.env['sign.request'].with_context(no_sign_mail=True).create({
            'anomaly_id': self.id,
            'reference': reference_name,
            'request_item_ids': [(0, 0, {
                'partner_id': self.purchaser_id.id,
                'role_id': 3,
        })],
            'template_id': template_id,
        })
        _logger.info("Stampo il sign_request")
        _logger.info(sign_request.id)
        request_item_id = self.env['sign.request'].search_read([('id', '=', sign_request.id)],['request_item_ids'])[0]['request_item_ids'][0]
        _logger.info(request_item_id)
        _logger.info(self.env['sign.request.item'].search_read([('id', '=', request_item_id)]))
        record = self.env['sign.request.item'].browse(request_item_id)
        _logger.info(record)
        email = self.env['res.partner'].search_read([('id', '=', self.purchaser_id.id)], ['email_personale'])[0]['email_personale']
        _logger.info(email)

        record.write({'signer_email': email})
        record.send_signature_accesses()
        sign_template = self.env['sign.template'].browse(template_id)
        sign_template.write({'active': False})
        self.state = 'reported'
        attachment_id = self.env['documents.document'].search_read([('tag_ids', '=', 29),('service_id.id', '=', self.id)], ['attachment_id'])[0]['attachment_id'][0]
        self.send_attachment_with_email(attachment_id)
        


    def cancelled(self):
        self.state = 'cancelled'

    def check_data(self):
        is_attachment = self.env['documents.document'].search_read([('tag_ids', '=', 29),('service_id.id', '=', self.id)], ['attachment_id'])

        if is_attachment == []:
            raise ValidationError(_("Non c'è alcun verbale allegato."))
        if self.purchaser_id.name == False:
            raise ValidationError(_("Non è stato inserito alcun autista."))
        if self.city_id.name == False:
            raise ValidationError(_("Non è stata selezionata alcuna città."))
        email = self.env['res.partner'].search_read([('id', '=', self.purchaser_id.id)], ['email_personale'])[0]['email_personale']
        if email == False:
            raise ValidationError(_("Il res.partner non ha una mail personale inserita."))
        # Controllo se il res.partner ha dipendenti collegati con contratti attivi
        contract_active = self.env['hr.employee'].search_read([('address_home_id', '=', self.purchaser_id.id)])
        _logger.info("*****************************")
        _logger.info(contract_active)
        if contract_active == []:
            raise ValidationError(_("L'autista non ha alcun contratto attivo."))

    
    # FUNZIONE DI PROVA
    def check_action(self):
        interinale = self.check_interinale_a()
        
        _logger.info(interinale)



    # Controllo se l'autista ha contratti attivi. Nel caso ci fossero controllo se è sotto interinale, altrimenti mostro un warning avvisando che non è in forza lavoro.
    def check_interinale_a(self):
        contacts = ""
        employees = self.env['hr.employee'].search_read([('address_home_id', '=', self.purchaser_id.id), '|',('active', '=', True), ('active', '=', False)])
        for employee in employees:
            for contract_id in employee['contract_ids']:
                _logger.info(contract_id)
                contract = self.env['hr.contract'].search_read([('id', '=', contract_id)])
                _logger.info(contract[0]['state'])
                # Controllo se il contratto è attivo
                if contract[0]['state'] == 'open':
                    _logger.info("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
                    _logger.info(employee)
                    if employee['interinale'] == False:
                        _logger.info(f"Il dipendente è assunto diretto {employee['interinale']}")
                        return False
                    else:
                        _logger.info(f"Il dipendente è assunto tramite azienda interinale {employee['interinale']}")
                        # Trovo i contatti della sede
                        interinale = self.env['hr.interinale'].search_read([('id', '=', employee['interinale'][0])])
                        _logger.info("SONO QUIIIIIIIII")
                        _logger.info(interinale[0]['res_partner_id'][1])
                        test = self.env['hr.interinale.contatti'].search_read()
                        for record in test:
                            _logger.info(record)
                            a = self.env['res.partner'].search([('id', '=', record['res_partner_id'][0]),('parent_id', '=', interinale[0]['res_partner_id'][1])])
                            _logger.info(a['id'])
                            if a['id'] != False:
                                email = self.env['res.partner'].search_read([('id', '=', a['id'])])[0]['email']
                                _logger.info(email)
                                contacts += email + "; "
                        _logger.info(contacts)
                        return contacts
                  

    
    
    # Controllo quale fosse il dipendente in essere al momento dell'evento e controllo se sia un dipendente interinale o meno
    def check_interinale(self):
        contacts = ""
        employees = self.env['hr.employee'].search_read([('address_home_id', '=', self.purchaser_id.id), '|',('active', '=', True), ('active', '=', False)])
        _logger.info('$$$$$$$$$$')
        for employee in employees:
            _logger.info(employee)
            for contract_id in employee['contract_ids']:
                _logger.info(contract_id)
                contract = self.env['hr.contract'].search_read([('id', '=', contract_id)])
                start_contract = contract[0]['date_start']
                end_contract = contract[0]['date_end']
                _logger.info(contract)
                _logger.info(f"inizio contratto {start_contract}")
                _logger.info(f"fine contratto {end_contract}")
                _logger.info(f"Data evento {self.date}")
            if end_contract != False:
                if self.date.date() >= start_contract and self.date.date() <= end_contract:
                    _logger.info(f"QUESTO È IL CONTRATTO GIUSTO")
                    _logger.info(f"l'id dell'hr employee attivo è {employee['id']}")
                    # controllo se è interinale
                    if employee['interinale'] == False:
                        _logger.info(f"Il dipendente è assunto diretto {employee['interinale']}")
                        # Se è assunto come interinale procedo con il passaggio delle informazioni
                        return False
                    else:
                        _logger.info(f"Il dipendente è assunto tramite azienda interinale {employee['interinale']}")
                        # Trovo i contatti della sede
                        interinale = self.env['hr.interinale'].search_read([('id', '=', employee['interinale'][0])])
                        _logger.info("SONO QUIIIIIIIII")
                        _logger.info(interinale[0]['res_partner_id'][1])
                        test = self.env['hr.interinale.contatti'].search_read()
                        for record in test:
                            _logger.info(record)
                            a = self.env['res.partner'].search([('id', '=', record['res_partner_id'][0]),('parent_id', '=', interinale[0]['res_partner_id'][1])])
                            _logger.info(a['id'])
                            if a['id'] != False:
                                email = self.env['res.partner'].search_read([('id', '=', a['id'])])[0]['email']
                                _logger.info(email)
                                contacts += email + "; "
                        _logger.info(contacts)
                        return contacts
                else:
                    _logger.info(f"questo contratto non è quello giusto")




    
    ######################
    ######################
    #    SINISTRI        #
    ######################
    ######################

    # Alla creazione di una anomalia di tipo "Sinistro" bisogna creare un attività che ricordi di completare l'inserimento dei dati
    def create_reminder(self, vals_list, res):
        # Il cdc va pescato dal viaggio associato o (come seconda opzione) dal contratto di disponibilità
        # Verifico se ci sono viaggi associati
        if vals_list[0]['trip_id'] != False: 
            # Recupero il cdc associato al viaggio
            _logger.info("CERCO L'ID CDC")
            cdc_id = self.env['gtms.trip'].search_read([('id', '=', vals_list[0]['trip_id'])], ['organization_id'])
        else:
            # recupero il cdc dall'ultimo contratto di disponibilità
            cdc_id = self.env['fleet.vehicle.log.contract'].search_read([('vehicle_id', '=', vals_list[0]['vehicle_id']), ('cost_subtype_id', '=', 47)], order='id desc',limit=1)
        helpdesk_id = self.env['helpdesk.team'].search_read([('organization_id', '=', cdc_id[0]['organization_id'][0])])
        
        _logger.info(cdc_id[0]['organization_id'][0])
        _logger.info(helpdesk_id)
        if vals_list[0]['service_type_id'] == 9:
            _logger.info("DEVO CREARE UN REMINDER")
            for user in helpdesk_id[0]['message_partner_ids']:
                user_id = self.env['res.users'].search_read([('partner_id', '=', user)], ['id'])
                _logger.info(user_id[0]['id'])
                alert = self.env['mail.activity'].create({
                    'res_name': 'Completamento sinistro ' + str(res['id']),
                    'activity_type_id': 26,
                    'user_id': user_id[0]['id'],
                    'res_model_id': 383, # id di fleet.vehicle.log.service
                    'res_id': res['id'],
                    'note': "<p style='margin-bottom:0px'>Per procedere allo step 'Segnalato' il sinistro deve essere completato con le seguenti informazioni:</p><ul style='margin-bottom:0px'><li>Modulo dichiarazione danno</li><li>Note descrittive</li></ul><li>Eventuale CID</li><li>Eventuali foto</li>"
                })
                _logger.info(alert)


    # Controllo se ci sono attività del tipio "Sistemazione sinistro" ancora aperte e nel caso devono essere chiouse prima di passare dallo stato "Inserito" a "Segnalato"
    def check_open_activity(self):
        activity = self.env['mail.activity'].search([('res_id', '=', self.id), ('res_model_id', '=', 383), ('activity_type_id', '=', 26)])
        if activity != []:
            activity.unlink()
    # Controllo se il documento "Modulo dichiarazione danni" è già stato allegato al sinistro.
    def check_documents(self):
        dichiarazione_danno = self.env['documents.document'].search_read([('tag_ids', '=', 43),('service_id.id', '=', self.id)], ['attachment_id'])
        _logger.info(dichiarazione_danno)
        if dichiarazione_danno == []:
            raise ValidationError(_("Non c'è alcun modulo dichiarazione danno allegato."))
        else:
            return True


    # Segnalazione sinistro
    # Per procedere devo controllare che il sinistro sia stato gestito (modulo dichiarazione danno presente)
    def report_anomaly(self):
        document = self.check_documents()
        if document == True:
            # Visto che tutti i documenti obbligatori sono stati allegati è possibile procedere con la segnalazione del sinistro al fornitore dei mezzi e ad eventuale interinale
            
            # Recupero l'importo che dovrà essere addebitato
            deduction_ids = self.deduction_ids.ids
            total_import = 0.0
            for deduction_id in deduction_ids:
                total_import += self.env['deduction.deduction'].search([('id', '=', deduction_id), ('date', '!=', False)]).deduction_value
            _logger.info("importo totale %s", total_import)
            importo_formattato = "{:.2f}".format(total_import).replace(".", ",")
    
            # Recupero il valore della responsabilità
            if self.responsibility == 'byself':
                responsibility = "Propria"
            elif self.responsibility == 'byself_third':
                responsibility = "Propia e di terzi"
            elif self.responsibility == 'third':
                responsibility = "Terza"
            elif self.responsibility == 'unknown':
                responsibility = "Sconosciuta"
    
            # Recupero dell'allegato
            attachment_id = self.env['documents.document'].search_read([('tag_ids', '=', 43),('service_id.id', '=', self.id)], ['attachment_id'])[0]['attachment_id'][0]
            attachment_ids = self.env['documents.document'].search_read([('tag_ids', 'in', [43, 45, 57, 58]),('service_id.id', '=', self.id)], ['attachment_id']) # Gli allegati da inviare sono: Modulo dichiarazione danni, Foto sinistro, CAI, Denuncia polizia
            attach = []
            for attachments in attachment_ids:
                _logger.info(attachments)
                attach.append((4, attachments['attachment_id'][0]))
            # attach = self.env['documents.document'].search_read([('tag_ids', '=', 43),('service_id.id', '=', self.id)], ['attachment_id'])[0]
            _logger.info("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
            _logger.info(attachment_id)
            _logger.info(attach)
            _logger.info("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    
    
            
            # Recupero lista danni
            damages = self.env['reparation.reparation'].search_read([('fleet_vehicle_log_service_id', '=', self.id)])
            list_damages = ""
            for damage in damages:
                _logger.info(damage['damage_type_id'][1])
                list_damages += "<li>" + str(damage['damage_type_id'][1]) + "</li>"
            # Recupero l'interinale
            interinale = self.check_interinale_a()
            # Se è interinale e la responsabilità non è "Sconosciuta" o di "Terzi" procedo con l'invio della comunicazione
            if interinale != [] and self.responsibility not in ['unnknown','third']:
                # Siccome il dipendente è attualmente interinale, bisognerà avvisare del sinistro l'interinale.
                body_interinale = f"""<p>Alla cortese attenzione del Responsabile Risorse Umane,</br>di seguito riepilogo sinistro:</br></br><b>Data/Ora: </b>{self.date.strftime('%d/%m/%Y %H:%M')}</br><b>Veicolo: </b>{self.vehicle_id.license_plate}</br><b>Autista: </b>{self.purchaser_id.name}</br><b>Responsabilità: </b>{responsibility}</br></br></br><p><b>Danni mezzo proprio ed eventuali parti coinvolte:</b><ul>{list_damages}</ul></p>
    <p><U>Potete procedere alla trattenuta della franchigia pari a € {importo_formattato},eventuali rateizzazioni verranno comunicate come di consueto a mezzo Timesheet</U></p>
    <p><b>Vi ricordo come da regolamento aziendale firmato dalla risorsa che le trattenute potranno avvenire anche in deroga ai limiti legali imposti.</b></p><br><p>In allegato la documentazione attestante il fatto.</p></br><p>Estratto regolamento aziendale: "Avuto riguardo alla non operabilità dei presupposti legali ex art. 1246 c.c. e art. 545 c.p.c. presupponenti ai fini di una compensazione tecnica, l’autonomia dei rapporti cui si riferiscono i contrapposti crediti delle parti e non operanti quando essi nascano dal medesimo rapporto, comportando soltanto un mero accertamento contabile di dare e avere, la relativa compensazione “tecnica” potrà avvenire anche in deroga ai limiti legali imposti e, dunque, anche in un’unica soluzione ed a prescindere dalle trattenute in corso per eventuali cessioni di credito e/o di pignoramento dello stipendio.</p></br></br><p>Futura</p>"""
                _logger.info(body_interinale)
                mail_values = {
                    'subject': f'Contravvenzione ns. rif. {str(self.id)} - Verbale n°  {self.description}  - {self.purchaser_id.name}',
                    'email_from': 'noreply@futurasl.com',
                    'email_to': interinale,
                    'email_cc': 'catchall@futurasl-stage.odoo.com',
                    'model': 'fleet.vehicle.log.services',
                    'res_id': self.id,
                    'body_html': body_interinale,
                    'attachment_ids': attach,  # Aggiungi l'allegato all'email
                }
        
                mail = self.env['mail.mail'].sudo().create(mail_values)
                mail.send()
    
            
            # Comunicazione al locatore dei mezzi
            # Recupero l'ultimo contratto di gli indirizzi mail del locatore
            
            body_locatore = f"""<p>Buongiorno,</br>
    di seguito riepilogo sinistro</p></br><p><b>Data/Ora: </b>{self.date.strftime('%d/%m/%Y %H:%M')}</br><b>Autista: </b>{self.purchaser_id.name}</br><b>Responsabilità: </b>{responsibility}</br></p><p><b>Danni mezzo proprio:</b><ul>{list_damages}</ul></p><p><b><U>Per questo sinistro ho bisogno di ricevere quantificazione del danno entro 5 giorni lavorativi dalla presente, oltre questo termine eventuali addebiti verranno respinti .
    In allegato la documentazione attestante il fatto</U></b></p></br></br><p>Futura</p>"""
            _logger.info(body_locatore)
            mail_values = {
                'subject': f'Contravvenzione ns. rif. {str(self.id)} - Verbale n°  {self.description}  - {self.purchaser_id.name}',
                'email_from': 'noreply@futurasl.com',
                'email_to': 'lcocozza93@icloud.com',
                'email_cc': 'catchall@futurasl-stage.odoo.com',
                'model': 'fleet.vehicle.log.services',
                'res_id': self.id,
                'body_html': body_locatore,
                'attachment_ids': [(4, attachment_id)],  # Aggiungi l'allegato all'email
            }
    
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
    
            # Scrivo nel chatter cosa ha appena fatto l'utente
            partner_id = self.env['res.users'].browse(self.env.uid).partner_id.id
            if interinale == []:
                self.env['mail.message'].create({'model': 'fleet.vehicle.log.services','res_id': self.id,'author_id': partner_id,'body': "<p>Ho appena inviato la seguente mail al locatore del mezzo:</p><p>Segnalazione apertura sinistro</p>"})
            else:
                self.env['mail.message'].create({'model': 'fleet.vehicle.log.services','res_id': self.id,'author_id': partner_id,'body': "<p>Ho appena inviato la seguente mail all'interinale e al locatore del mezzo:</p><p>Segnalazione apertura sinistro</p>"})
            self[0].state = 'reported'
    
            # Una volta cambiato lo stato in "Segnalato" devo cancellare eventuali attività
            self.check_open_activity()



    def to_processed(self):
        have_deduction = self.env['deduction.deduction'].search_read([('fleet_vehicle_log_service_id', '=', self.id)])
        if have_deduction != []:
            self[0].state = 'running'
        else:
            raise ValidationError(_("Non ci sono addebiti al dipendente associati all'anomalia."))



        ################################
        ################################
        #  MANUTENZIONE STRAORDINARIA  #
        ################################
        ################################
        
    def test_action(self):
        _logger.info("TEST ACTION")




##################
#    DA FARE     #
##################
# - Mettere il campo locator_location visibile solo bnei contratti di noleggio e noleggio scorta
# - Recuperare la sede del locatore per poter inviare la mai agli indirizzi corretti.
