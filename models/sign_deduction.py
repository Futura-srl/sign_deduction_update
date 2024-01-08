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
        self.env['mail.message'].create({'model': 'fleet.vehicle.log.services','res_id': self.id,'author_id': partner_id,'message_type': 'comment','body': "<p>Ho appena inviato le seguenti email:</p><p>Comunicazione da far firmare al dipendente</p><p>Copia del verbale al dipendente</p>"})

        # Invia l'email con l'allegato all'interinale
        mail_values = {
            'subject': f'Contravvenzione ns. rif. {str(self.id)} - Verbale n°  {self.description}  - {self.purchaser_id.name}',
            'email_from': 'noreply@futurasl.com',
            'email_to': email,
            'email_cc': 'catchall@futurasl-stage.odoo.com',
            'model': 'fleet.vehicle.log.services',
            'res_id': self.id,
            'body_html': body_interinale,
            'attachment_ids': [(4, attachment_id)],  # Aggiungi l'allegato all'email
        }

        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()
        partner_id = self.env['res.users'].browse(self.env.uid).partner_id.id
        self.env['mail.message'].create({'model': 'fleet.vehicle.log.services','res_id': self.id,'author_id': partner_id,'body': "<p>Ho appena inviato le seguenti email:</p><p>Comunicazione da far firmare al dipendente</p><p>Copia del verbale al dipendente e all'interinale</p>"})
    
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
        email = self.env['res.partner'].search_read([('id', '=', self.purchaser_id.id)], ['email_personale'])[0]['email_personale']

        if is_attachment == []:
            raise ValidationError(_("Non c'è alcun verbale allegato."))
        if self.purchaser_id.name == False:
            raise ValidationError(_("Non è stato inserito alcun autista."))
        if self.city_id.name == False:
            raise ValidationError(_("Non è stata selezionata alcuna città."))
        if email == False:
            raise ValidationError(_("Il res.partner non ha una mail personale inserita."))



