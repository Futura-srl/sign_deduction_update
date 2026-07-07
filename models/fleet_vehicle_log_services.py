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

    state = fields.Selection(
        [('new', 'Inserito'), ('reported', 'Segnalato'), ('running', 'Processato'), ('done', 'Completato'),
         ('cancelled', 'Annullato')], readonly=True, tracking=True)
    # groups_ids = fields.Char(string='Groups of the User', compute='_compute_groups_admin', store=False)
    is_admin = fields.Boolean(compute='_compute_groups_admin', store=False)
    is_fleet_admin = fields.Boolean(compute='_compute_groups_fleet_admin', store=False)
    is_fleet_rop = fields.Boolean(compute='_compute_groups_fleet_rop', store=False)
    replacement_start_date = fields.Datetime(string="Replacement Start Datetime")
    replacement_end_date = fields.Datetime(string="Replacement Start Datetime")
    email_ids = fields.One2many('mail.mail', 'res_id', string='Emails',
                                domain="[('model','=', 'fleet.vehicle.log.services'), ('res_id', '=', id)]")
    signed_document = fields.Boolean(default=False, readonly=True)
    # Add select to chose if the service is to be charged or not
    to_be_charged = fields.Selection([('yes', 'Yes'), ('no', 'No')], string='To be charged?', default=False,
                                     tracking=True,
                                     help="Select if the service is to be charged to the customer or not.")
    motivation_of_charge = fields.Text(string='Motivation of not charge',
                                       help="Please specify the reason why it should not be charged.",
                                       tracking=True)
    employee_interinale = fields.Boolean(string="Employee Interinale", compute="_compute_employee_interinale",
                                         store=True, help="Check if the employee is an interinale.")
    email_interinalle = fields.Boolean(string="Email Interinale",
                                       help="Check if the employee is an interinale and has an email.")

    is_ztl_present = fields.Boolean(compute='_compute_is_ztl', store=False)
    all_active_ztl = fields.Many2many('fleet.vehicle.log.contract')



    @api.model_create_multi
    def create(self, vals_list):
        res = super(FleetVehicleLogServices, self).create(vals_list)
        if res:
            if res['service_type_id'].id == 9:
                self.create_reminder(vals_list, res)
        return res

    @api.depends('groups_ids')
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
            record.is_fleet_admin = user.has_group('fleet.fleet_group_manager')

    @api.depends('create_date')
    def _compute_groups_fleet_rop(self):
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

    @api.depends('purchaser_id')
    def _compute_employee_interinale(self):
        for record in self:
            # Trovo tutti i dipendenti associati al partner
            employees = self.env['hr.employee'].sudo().search(
                [('address_home_id', '=', record.purchaser_id.id), ('active', '=', True)])
            for employee in employees:
                # Controllo se il dipendente oggi ha un contratto attivo
                active_contract = self.env['hr.contract'].sudo().search(
                    [('employee_id', '=', employee.id), ('date_start', '<=', date_today), '|',
                     ('date_end', '>=', date_today), ('date_end', '=', False)])
                if active_contract:
                    # Se ho trovato un contratto attivo, imposto il campo a True
                    record.employee_interinale = True
                    break

    ####################
    ####################
    #     MULTE        #
    ####################
    ####################


    # Avviso chi inserisce la multa se la multa è di tipologia is_ztl e il mezzo ha contratti ztl attivi in quel periodo
    @api.depends('violation_ids', 'date')
    def _compute_is_ztl(self):
        all_ztl_type = self.env['fleet.service.type'].sudo().search([('is_ztl', '=', True)])
        active_ztl = []
        for record in self:
            is_ztl = False
            for violation in record.violation_ids:
                if violation.is_ztl:
                    # _logger.info("Ho trovato una violazione con ZTL")
                    # Controllo se il mezzo aveva coperture ZTL attive in quel giorno
                    active_ztl_contracts = self.env['fleet.vehicle.log.contract'].sudo().search(
                        [('vehicle_id', '=', record.vehicle_id.id),
                         ('cost_subtype_id', 'in', all_ztl_type.ids),
                         ('start_date', '<=', record.date.date()),
                         '|',
                         ('expiration_date', '>=', record.date.date()),
                         ('expiration_date', '=', False)]
                    )
                    if active_ztl_contracts:
                        # _logger.info("Ho trovato un contratto ZTL attivo per il mezzo in quel giorno")
                        # _logger.info(active_ztl_contracts)
                        is_ztl = True
                        active_ztl = active_ztl_contracts.ids
                        break
            record.is_ztl_present = is_ztl
            record.all_active_ztl = [(6, 0, active_ztl)]


    @api.onchange('violation_ids', 'is_ztl_present')
    def _onchange_violation_ids(self):
        if self.is_ztl_present:

            # _logger.info(f"Stampo tutti le ztl trovate attive in quel giorno")
            # _logger.info(self.all_active_ztl)
            messages = ""
            for ztl in self.all_active_ztl:
                # _logger.info(f"Stampo singolo contratto ztl")
                # _logger.info(" - " + ztl.cost_subtype_id.name + " dal " + str(ztl.start_date) + " al " + str(ztl.expiration_date))
                messages += " - " + ztl.cost_subtype_id.name + " dal " + str(ztl.start_date) + " al " + str(ztl.expiration_date) + "\n"
            return {
                'warning': {
                    'title': 'Attenzione',
                    'message': f"Vi erano delle ZTL attive sul mezzo al momento dell'infrazione:\n{messages}"
                }
            }

    def confirm_signed_document(self):
        for record in self:
            if record.signed_document == False:
                record.signed_document = True
            else:
                record.signed_document = False

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
            doc_base64 = self.env['ir.attachment'].sudo().browse(163362)  # Template da 1 pagina
        else:
            doc_base64 = self.env['ir.attachment'].sudo().browse(163364)  # Template da 2 pagine
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
            _logger.info(self.env['deduction.deduction'].sudo().search(
                [('id', '=', deduction_id), ('date', '!=', False)]).sudo().deduction_value)
            total_import += self.env['deduction.deduction'].search(
                [('id', '=', deduction_id), ('date', '!=', False)]).sudo().deduction_value
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
            "[DATA_EVENTO]": str(self.date.strftime('%d/%m/%Y')),
            "[LUOGO]": self.city_id.name,
            "[TARGA]": self.vehicle_id.license_plate,
            "[IMPORTO]": str(importo_formattato),
            "[NUMERO_VERBALE]": self.description + " del " + str(self.date.strftime('%d/%m/%Y')),
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
        return template.id, attachment_id

    def send_attachment_with_email(self, attachment_id, attachment_for_rop_id=""):
        # Recupero i rop che dovranno ricevere anche loro la mail
        organization_id = self.env['gtms.trip'].sudo().search_read([('id', '=', self.trip_id.id)], ['organization_id'])
        _logger.info(organization_id[0]['organization_id'][0])
        rop_ids = self.env['helpdesk.team'].sudo().search_read(
            [('organization_id', '=', organization_id[0]['organization_id'][0])], ['message_partner_ids'])
        _logger.info(rop_ids[0])
        mail_rop = ""
        rop_ids = self.env['res.partner'].sudo().search([('id', 'in', rop_ids[0]['message_partner_ids'])])
        # mail += self.env['res.partner'].search([('id', '=', rop_ids['message_partner_ids'])])
        for rop_id in rop_ids:
            _logger.info(f"Stampo ROP_ID {rop_id.email}")

            mail_rop += rop_id['email'] + "; "
        _logger.info(mail_rop)
        # Controllo se è interinale
        is_interinal = self.env['hr.employee'].sudo().search_read(
            [('address_home_id', '=', self.purchaser_id.id), ('active', '=', True)])
        email = self.env['res.partner'].sudo().search_read([('id', '=', self.purchaser_id.id)], ['email_personale'])[0][
            'email_personale']
        _logger.info(f"La mail va inviata a {email}")

        deduction_ids = self.deduction_ids.ids
        total_import = 0.0
        for deduction_id in deduction_ids:
            total_import += self.env['deduction.deduction'].search(
                [('id', '=', deduction_id), ('date', '!=', False)]).deduction_value
        _logger.info("importo totale %s", total_import)
        importo_formattato = "{:.2f}".format(total_import).replace(".", ",")
        if self.deduction_point > 0:
            body_interinale = f"""<p>Buongiorno,<br />in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di competenza della risorsa {self.purchaser_id.name} in quanto al momento della violazione avvenuta in data/ore (data Evento) si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione comporta la decurtazione di punti {self.deduction_point}.</p>
<p><b>Qualora la contravvenzione comporti la decurtazione di Punti vi chiediamo entro 5 giorni di rispondere allegando alla presente:</b>
<ul>
    <li>Copia fronte e retro della patente sulla stessa facciata con scritto di proprio pugno dall’autista la seguente frase 'Io sottoscritto {self.purchaser_id.name} nato a (paese e provincia di nascita) residente a (paese e provincia di residenza) in via (via) dichiaro che la copia del presente documento (indicare tipo documento) n° (numero documento) è conforme all'originale in mio possesso. (data e firma leggibile)'.</li>
    <li>Modulo comunicazione dati conducente allegata al presente verbale correttamente compilato e firmato.</li>
</ul></p>
<p><b>Vi chiedo di procedere al rilascio della vostra contestazione ed operare la relativa trattenuta dell’importo {importo_formattato}</b> in base a quanto vi verrà quantificato nel Timesheet come di consueto, da sommarsi qualora la contravvenzione preveda la decurtazione di punti e la risorsa non intenda comunicare i propri dati ulteriori 220,00€ a fronte della sanzione che riceveremo per la mancata comunicazione dei dati del conducente all’ente accertatore.</p>
<p>Vi informiamo che è stata inoltrata la contestazione dell’evento da firmare per presa visione alla risorsa all’indirizzo (indirizzo mail dipendente).</p>
<p>Per eventuali contestazioni vi chiediamo di rispondere sempre a questa mail.</p>
<br /><br />
<p>Futura</p>"""

            body_employee = f'''<p>Buongiorno,<br />in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di Vostra competenza in quanto al momento della violazione avvenuta in data/ore {self.date} si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione comporta la decurtazione di punti {self.deduction_point}.</p>
<p><b>Qualora la contravvenzione comporti la decurtazione di Punti vi chiediamo entro 5 giorni di rispondere allegando alla presente:</b>
<ul>
    <li>Copia fronte e retro della patente sulla stessa facciata con scritto di proprio pugno dall’autista la seguente frase 'Io sottoscritto {self.purchaser_id.name} nato a (paese e provincia di nascita) residente a (paese e provincia di residenza) in via (via) dichiaro che la copia del presente documento (indicare tipo documento) n° (numero documento) è conforme all'originale in mio possesso. (data e firma leggibile)'.</li>
    <li>Modulo comunicazione dati conducente allegata al presente verbale correttamente compilato e firmato.</li>
</ul></p>
<p>Al presente verbale saranno da sommarsi qualora la contravvenzione preveda la decurtazione di punti e Lei non intenda comunicare i propri dati ulteriori 220,00€ a fronte della sanzione che riceveremo per la mancata comunicazione dei dati del conducente all’ente accertatore.</p>
<p>Riceverà ulteriore mail con un link che riporterà alla contestazione da firmare per presa visione, tale firma non esclude l’eventuale addebito</p>
<p>Per eventuali contestazioni vi chiediamo di far riferimento al vostro responsabile di sede.</p>
<br /><br />
<p>Futura</p>'''
            body_rop = f"""<p>Buongiorno,<br />in allegato la documentazione da far firmare all'autista relativa alla contravvenzione del codice della strada n° {self.description} avvenuta in data/ore {self.date} con il mezzo targato {self.vehicle_id.license_plate}, tale contravvenzione comporta la decurtazione di punti.</p>
<br />
<p>Futura</p>"""
        else:
            body_employee = f"""<p>Buongiorno,<br />in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di Vostra competenza in quanto al momento della violazione avvenuta in data/ore {self.date} si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione non comporta la decurtazione di punti.</p>
<p>Riceverà ulteriore mail con un link che riporterà alla contestazione da firmare per presa visione, tale firma non esclude l’eventuale addebito</p>
<p>Per eventuali contestazioni vi chiediamo di far riferimento al vostro responsabile di sede.</p>
<br />
<p>Futura</p>"""
            body_rop = f"""<p>Buongiorno,<br />in allegato la documentazione da far firmare all'autista relativa alla contravvenzione del codice della strada n° {self.description} avvenuta in data/ore {self.date} con il mezzo targato {self.vehicle_id.license_plate}, tale contravvenzione non comporta la decurtazione di punti.</p>
<br />
<p>Futura</p>"""
            body_interinale = f"""<p>Buongiorno,<br />in allegato la documentazione relativa alla contravvenzione del codice della strada n° {self.description} di competenza della risorsa {self.purchaser_id.name} in quanto al momento della violazione avvenuta in data/ore {self.date} si trovava alla guida del mezzo {self.vehicle_id.license_plate}, tale contravvenzione non comporta la decurtazione di punti.</p>
<p><b>Vi chiedo di procedere al rilascio della vostra contestazione ed operare la relativa trattenuta dell’importo {importo_formattato}</b> in base a quanto vi verrà quantificato nel Timesheet come di consueto.</p>
<p>Vi informiamo che è stata inoltrata la contestazione dell’evento da firmare per presa visione alla risorsa all’indirizzo (indirizzo mail dipendente).</p>
<p>Per eventuali contestazioni vi chiediamo di rispondere sempre a questa mail.</p>
<br />
<p>Futura</p>"""

        # Invia l'email con l'allegato al dipendente
        mail_values = {
            'subject': f'Contravvenzione ns. rif. {str(self.id)} - Verbale n°  {self.description}  - {self.purchaser_id.name}',
            'email_from': 'noreply@futurasl.com',
            'email_to': email,
            'email_cc': 'catchall@futurasl.odoo.com',
            'reply_to': 'catchall@futurasl.odoo.com',
            'model': 'fleet.vehicle.log.services',
            'res_id': self.id,
            'body_html': body_employee,
            'attachment_ids': [(4, attachment_id)],  # Aggiungi l'allegato all'email
        }
        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()

        # Invia l'email con l'allegato al dipendente
        mail_rop_values = {
            'subject': f'Contravvenzione ns. rif. {str(self.id)} - Verbale n°  {self.description}  - {self.purchaser_id.name}',
            'email_from': 'noreply@futurasl.com',
            'email_to': mail_rop,
            'reply_to': 'catchall@futurasl.odoo.com',
            'model': 'fleet.vehicle.log.services',
            'res_id': self.id,
            'body_html': body_rop,
            'attachment_ids': [(4, attachment_for_rop_id)],  # Aggiungi l'allegato all'email
        }
        mail = self.env['mail.mail'].sudo().create(mail_rop_values)
        mail.send()

        partner_id = self.env['res.users'].sudo().browse(self.env.uid).partner_id.id
        self.env['mail.message'].create(
            {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
             'message_type': 'comment',
             'body': "<p>Ho appena inviato le seguenti email al dipendente:</p><p>Comunicazione da far firmare al dipendente</p><p>Copia del verbale</p>"})

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
                'email_cc': 'catchall@futurasl.odoo.com',
                'reply_to': 'catchall@futurasl.odoo.com',
                'model': 'fleet.vehicle.log.services',
                'res_id': self.id,
                'body_html': body_interinale,
                'attachment_ids': [(4, attachment_id)],  # Aggiungi l'allegato all'email
            }

            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
            partner_id = self.env['res.users'].browse(self.env.uid).partner_id.id
            self.env['mail.message'].sudo().create(
                {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                 'body': "<p>Ho appena inviato la seguente mail all'interinale:</p><p>Copia del verbale</p>"})

    def create_document_request_sign(self):
        if self.to_be_charged == False:
            raise ValidationError(_("Non è stata inserita alcuna motivazione di addebito."))
        self.check_data()
        template_id, attachment_for_rop_id = self.add_template_for_sign()
        _logger.info(template_id)
        reference_name = str(self.id) + " " + str(self.service_type_id.name) + " " + str(self.description)
        sign_request = self.env['sign.request'].with_user(2).with_context(no_sign_mail=True).create({
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
        request_item_id = self.env['sign.request'].search_read([('id', '=', sign_request.id)], ['request_item_ids'])[0][
            'request_item_ids'][0]
        _logger.info(request_item_id)
        _logger.info(self.env['sign.request.item'].search_read([('id', '=', request_item_id)]))
        record = self.env['sign.request.item'].browse(request_item_id)
        _logger.info(record)
        email = self.env['res.partner'].search_read([('id', '=', self.purchaser_id.id)], ['email_personale'])[0][
            'email_personale']
        _logger.info(email)

        record.write({'signer_email': email})
        record.send_signature_accesses()
        sign_template = self.env['sign.template'].browse(template_id)
        sign_template.write({'active': False})
        self.state = 'reported'
        attachment_id = \
        self.env['documents.document'].search_read([('tag_ids', '=', 29), ('service_id.id', '=', self.id)],
                                                   ['attachment_id'])[0]['attachment_id'][0]
        self.send_attachment_with_email(attachment_id, attachment_for_rop_id)

    def cancelled(self):
        self.state = 'cancelled'

    def check_data(self):
        is_attachment = self.env['documents.document'].search_read(
            [('tag_ids', '=', 29), ('service_id.id', '=', self.id)], ['attachment_id'])

        if is_attachment == []:
            raise ValidationError(_("Non c'è alcun verbale allegato."))
        if self.purchaser_id.name == False:
            raise ValidationError(_("Non è stato inserito alcun autista."))
        if self.city_id.name == False:
            raise ValidationError(_("Non è stata selezionata alcuna città."))
        email = self.env['res.partner'].search_read([('id', '=', self.purchaser_id.id)], ['email_personale'])[0][
            'email_personale']
        if email == False:
            raise ValidationError(_("Il res.partner non ha una mail personale inserita."))
        # Controllo se il res.partner ha dipendenti collegati con contratti attivi
        contract_active = self.env['hr.employee'].sudo().search_read([('address_home_id', '=', self.purchaser_id.id)])
        if contract_active:
            _logger.info(contract_active[0]['contract_id'][0])
            contract = self.env['hr.contract'].sudo().search([('id', '=', contract_active[0]['contract_id'][0])])
            _logger.info(contract.state)
            if contract.state != 'open':
                raise ValidationError(_("L'autista non ha alcun contratto attivo."))
        else:
            raise ValidationError(_("L'autista non ha alcun dipendente attivo."))

    # FUNZIONE DI PROVA
    def check_action(self):
        interinale = self.check_interinale_a()

        _logger.info(interinale)

    # Controllo se l'autista ha contratti attivi. Nel caso ci fossero controllo se è sotto interinale, altrimenti mostro un warning avvisando che non è in forza lavoro.
    def check_interinale_a(self):
        contacts = set()
        contacts_str = ""
        if self.purchaser_id.is_esterno:
            return False
        employees = self.env['hr.employee'].search_read(
            [('address_home_id', '=', self.purchaser_id.id), '|', ('active', '=', True), ('active', '=', False)])
        for employee in employees:
            for contract_id in employee['contract_ids']:
                _logger.info(contract_id)
                contract = self.env['hr.contract'].sudo().search_read([('id', '=', contract_id)])
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
                        interinale = self.env['hr.interinale'].sudo().search_read([('id', '=', employee['interinale'][0])])
                        _logger.info("SONO QUIIIIIIIII")
                        _logger.info(interinale[0]['res_partner_id'][1])
                        test = self.env['hr.interinale.contatti'].sudo().search_read()
                        for record in test:
                            _logger.info(record)
                            a = self.env['res.partner'].search([('id', '=', record['res_partner_id'][0]),
                                                                ('parent_id', '=', interinale[0]['res_partner_id'][1])])
                            _logger.info(a['id'])
                            if a['id'] != False:
                                email = self.env['res.partner'].search_read([('id', '=', a['id'])])[0]['email']
                                _logger.info(email)
                                contacts.add(email)
                        _logger.info(contacts)
                        for contact in contacts:
                            contacts_str += str(contact + "; ")
                        return contacts_str

    # Controllo quale fosse il dipendente in essere al momento dell'evento e controllo se sia un dipendente interinale o meno
    def check_interinale(self):
        contacts = []
        contacts_str = ""
        employees = self.env['hr.employee'].search_read(
            [('address_home_id', '=', self.purchaser_id.id), '|', ('active', '=', True), ('active', '=', False)])
        _logger.info('$$$$$$$$$$')
        for employee in employees:
            _logger.info(employee)
            for contract_id in employee['contract_ids']:
                _logger.info(contract_id)
                contract = self.env['hr.contract'].sudo().search_read([('id', '=', contract_id)])
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
                        interinale = self.env['hr.interinale'].sudo().search_read([('id', '=', employee['interinale'][0])])
                        _logger.info("SONO QUIIIIIIIII")
                        _logger.info(interinale[0]['res_partner_id'][1])
                        test = self.env['hr.interinale.contatti'].sudo().search_read()
                        for record in test:
                            _logger.info(record)
                            a = self.env['res.partner'].search([('id', '=', record['res_partner_id'][0]),
                                                                ('parent_id', '=', interinale[0]['res_partner_id'][1])])
                            _logger.info(a['id'])
                            if a['id'] != False:
                                email = self.env['res.partner'].search_read([('id', '=', a['id'])])[0]['email']
                                _logger.info(email)
                                contacts.append(email + "; ")
                            _logger.info(contacts)
                            _logger.info(contacts)
                            contacts.unique()
                            for record_str in contacts:
                                _logger.info(record_str)
                                contacts_str += record_str
                        _logger.info(contacts_str)
                        return contacts_str
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
            cdc_id = self.env['fleet.vehicle.log.contract'].search_read(
                [('vehicle_id', '=', vals_list[0]['vehicle_id']), ('cost_subtype_id', '=', 47)], order='id desc',
                limit=1)
        helpdesk_id = self.env['helpdesk.team'].sudo().search_read([('organization_id', '=', cdc_id[0]['organization_id'][0])])

        if not helpdesk_id:
            raise ValidationError(
                _("Errore nella creazione dell'anomalia e del reminder. Non sei un ROP autorizzato. Per farsi aggiungere contattare raffaele.tesolin@futurasl.com o il 0431/611714."))

        _logger.info(cdc_id[0]['organization_id'][0])
        _logger.info(helpdesk_id)
        if vals_list[0]['service_type_id'] == 9:
            _logger.info("DEVO CREARE UN REMINDER")
            for user in helpdesk_id[0]['message_partner_ids']:
                user_id = self.env['res.users'].sudo().search_read([('partner_id', '=', user)], ['id'])
                _logger.info(user_id[0]['id'])
                alert = self.env['mail.activity'].create({
                    'res_name': 'Completamento sinistro ' + str(res['id']),
                    'activity_type_id': 26,
                    'user_id': user_id[0]['id'],
                    'res_model_id': 383,  # id di fleet.vehicle.log.service
                    'res_id': res['id'],
                    'note': "<p style='margin-bottom:0px'>Per procedere allo step 'Segnalato' il sinistro deve essere completato con le seguenti informazioni:</p><ul style='margin-bottom:0px'><li>Modulo dichiarazione danno</li><li>Note descrittive</li><li>Eventuale CID</li><li>Eventuali foto</li></ul>"
                })
                _logger.info(alert)

    # Controllo se ci sono attività del tipio "Sistemazione sinistro" ancora aperte e nel caso devono essere chiouse prima di passare dallo stato "Inserito" a "Segnalato"
    def check_open_activity(self):
        activity = self.env['mail.activity'].search(
            [('res_id', '=', self.id), ('res_model_id', '=', 383), ('activity_type_id', '=', 26)])
        if activity != []:
            activity.unlink()

    # Controllo se il documento "Modulo dichiarazione danni" è già stato allegato al sinistro.
    def check_documents(self):
        dichiarazione_danno = self.env['documents.document'].search_read(
            [('tag_ids', '=', 43), ('service_id.id', '=', self.id)], ['attachment_id'])
        _logger.info(dichiarazione_danno)
        if dichiarazione_danno == []:
            raise ValidationError(_("Non c'è alcun modulo dichiarazione danno allegato."))
        else:
            return True

    # Segnalazione sinistro
    # Per procedere devo controllare che il sinistro sia stato gestito (modulo dichiarazione danno presente)
    def report_anomaly(self):
        # Controllo se il dipendente e` un esterno
        is_employee_external = self.purchaser_id.is_esterno
        email_to_assurance = ""
        email_to = ""

        document = self.check_documents()
        if document == True:
            # Recupero i rop che dovranno ricevere anche loro la mail
            _logger.info("AAAAAAAAAAAAA")
            _logger.info(self.trip_id['id'])
            organization_id = self.env['gtms.trip'].search_read([('id', '=', self.trip_id['id'])], ['organization_id'])
            rop_ids = self.env['helpdesk.team'].sudo().search_read(
                [('organization_id', '=', organization_id[0]['organization_id'][1])], ['message_partner_ids'])

            # Visto che tutti i documenti obbligatori sono stati allegati è possibile procedere con la segnalazione del sinistro al fornitore dei mezzi e ad eventuale interinale

            # Recupero l'importo che dovrà essere addebitato
            deduction_ids = self.deduction_ids.ids
            total_import = 0.0
            for deduction_id in deduction_ids:
                total_import += self.env['deduction.deduction'].search(
                    [('id', '=', deduction_id), ('date', '!=', False)]).deduction_value
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
            attachment_id = \
            self.env['documents.document'].search_read([('tag_ids', '=', 43), ('service_id.id', '=', self.id)],
                                                       ['attachment_id'])[0]['attachment_id'][0]
            attachment_ids = self.env['documents.document'].search_read(
                [('tag_ids', 'in', [43, 59, 57, 58]), ('service_id.id', '=', self.id)], [
                    'attachment_id'])  # Gli allegati da inviare sono: Modulo dichiarazione danni, Foto sinistro, CAI, Denuncia polizia
            is_foto_sinistro = self.env['documents.document'].search_read(
                [('tag_ids', 'in', [59]), ('service_id.id', '=', self.id)], ['attachment_id'])
            is_cai = self.env['documents.document'].search_read(
                [('tag_ids', 'in', [57]), ('service_id.id', '=', self.id)], ['attachment_id'])
            is_denuncia = self.env['documents.document'].search_read(
                [('tag_ids', 'in', [58]), ('service_id.id', '=', self.id)], ['attachment_id'])
            attach = []
            for attachments in attachment_ids:
                _logger.info(attachments)
                attach.append((4, attachments['attachment_id'][0]))
            # attach = self.env['documents.document'].search_read([('tag_ids', '=', 43),('service_id.id', '=', self.id)], ['attachment_id'])[0]
            # _logger.info("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
            # _logger.info(attachment_id)
            # _logger.info(attach)
            # _logger.info("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

            # Recupero lista danni
            damages = self.env['reparation.reparation'].search_read([('fleet_vehicle_log_service_id', '=', self.id)])
            list_damages = ""
            for damage in damages:
                # _logger.info(damage['damage_type_id'][1])
                list_damages += "<li>" + str(damage['damage_type_id'][1]) + "</li>"
            # Recupero l'interinale
            interinale = self.check_interinale_a()
            # Se è interinale e la responsabilità non è "Sconosciuta" o di "Terzi" procedo con l'invio della comunicazione
            # _logger.info(
            #     f"STAMPO I VALORI DI is_employee_external {is_employee_external}, interinale {interinale} E self.responsibility {self.responsibility}")
            if is_employee_external == False and interinale != False and self.responsibility not in ['unnknown', 'third']:
                # Siccome il dipendente è attualmente interinale, bisognerà avvisare del sinistro l'interinale.
                body_interinale = f"""<p>Buongiorno,<br />
                                            di seguito riepilogo sinistro</p><br /><p><b>Data/Ora: </b>{self.date.strftime('%d/%m/%Y %H:%M')}<br /><b>Autista: </b>{self.purchaser_id.name}<br /><b>Responsabilità: </b>{responsibility}<br /></p><p><b>Danni mezzo proprio:</b><ul>{list_damages}</ul></p><p><b>Note: </b>{self.notes}</p><p><b><U>In allegato la documentazione attestante il fatto.</U></b></p><br /><br /><p>Futura</p>"""
                # _logger.info(body_interinale)
                mail_values = {
                    'subject': f'Sinistro rif.int. {str(self.id)} - interinale',
                    'email_from': 'catchall@futurasl.com',
                    'email_to': interinale,
                    'email_cc': 'catchall@futurasl.com',
                    'reply_to': 'catchall@futurasl.com',
                    'model': 'fleet.vehicle.log.services',
                    'res_id': self.id,
                    'body_html': body_interinale,
                    'attachment_ids': attach,  # Aggiungi l'allegato all'email
                }

                mail_interinale = self.env['mail.mail'].sudo().create(mail_values)
                # _logger.info(
                #     f"Creo la mail all'interinale perche il suo valore e' {interinale}\nValore di mail_interinale {mail_interinale}")
            # else:
            #     _logger.info(f"MAIL INTERINALE SALTATA")

            # Controllo se il mezzo ha come owner un'azienda interna
            # Comunicazione al locatore dei mezzi se il mezzo non appartiene ad un'azienda interna e ha un locatore, altrimenti avviso con un errore
            # Recupero l'ultimo contratto di gli indirizzi mail del locatore
            # _logger.info("CERCO I VEICOLI")
            vehicles = self.env['fleet.vehicle'].search_read([('id', '=', self.vehicle_id['id'])])
            # _logger.info(f"HO TROVATO I SEGUENTI VEICOLI {vehicles}")
            email_to = ""
            company = self.env['res.company'].search_read([], ['partner_id'])
            list_company_partner = []
            for company_partner in company:
                _logger.info(company_partner)
                list_company_partner.append(company_partner['partner_id'][0])
            for vehicle in vehicles:
                # _logger.info("VERIFICO SE IL MEZZO E` A NOLEGGIO O DI PROPRIETA`")
                # Controllo se il mezzo non ha come owner almeno una delle aziende interne
                is_rent = self.env['fleet.vehicle'].sudo().search(
                    [('id', '=', vehicle['id']), ('owner_id', 'not in', list_company_partner)])
                _logger.info("STAMPO is_rent {is_rent}")
                if is_rent:
                    # _logger.info("MEZZO A NOLEGGIO")
                    # Cerco i contratti attivi di noleggio, noleggio scorta e non contrattualizzato
                    contracts = self.env['fleet.vehicle.log.contract'].search_read(
                        [('vehicle_id', '=', vehicle['id']), ('cost_subtype_id', 'in', [83, 84, 85])], order='id desc')
                    # Se non esistono contratti attivi avviso
                    if not contracts:
                        raise ValidationError(
                            _("Non è stato possibile recuperare un contratto attivo di noleggio / noleggio scorta / non contrattualizzato."))
                    for contract in contracts:
                        _logger.info(contract['insurer_id'][0])
                        _logger.info(contract['locator_location'])
                        if contract['locator_location'] != False:

                            _logger.info(contract['locator_location'][0])
                            # controllo se l'id recuperato è presente in fleet.locator
                            is_locator = self.env['fleet.renter'].search_read(
                                [('res_partner_id', '=', contract['insurer_id'][0]),
                                 ('res_city_id.name', '=', contract['locator_location'][1])])
                        else:
                            raise ValidationError(_("Non è stato possibile recuperare il locatore del mezzo."))
                        if 'is_locator' in locals():
                            for record in is_locator:
                                _logger.info(record['email_list'])
                                email_to = record['email_list']
                        if email_to != "":
                            body_locatore = f"""<p>Buongiorno,<br />
                    di seguito riepilogo sinistro</p><br /><p><b>Data/Ora: </b>{self.date.strftime('%d/%m/%Y %H:%M')}<br /><b>Autista: </b>{self.purchaser_id.name}<br /><b>Responsabilità: </b>{responsibility}<br /></p><p><b>Danni mezzo proprio:</b><ul>{list_damages}</ul></p><p><b><U>Per questo sinistro ho bisogno di ricevere quantificazione del danno entro 5 giorni lavorativi dalla presente, oltre questo termine eventuali addebiti verranno respinti .
                    In allegato la documentazione attestante il fatto</U></b></p><br /><br /><p>Futura</p>"""
                            _logger.info(body_locatore)
                            mail_values = {
                                'subject': f'Sinistro rif.int. {str(self.id)} - locatore',
                                'email_from': 'catchall@futurasl.com',
                                'email_to': email_to,
                                'email_cc': 'catchall@futurasl.com',
                                'reply_to': 'catchall@futurasl.com',
                                'model': 'fleet.vehicle.log.services',
                                'res_id': self.id,
                                'body_html': body_locatore,
                                'attachment_ids': attach,  # Aggiungi l'allegato all'email
                            }

                            mail_locatore = self.env['mail.mail'].sudo().create(mail_values)
                            _logger.info(f"Creo la mail al locatore perche il suo valore e' {email_to}")
                            break
                        else:
                            raise ValidationError(
                                _("Non è stato possibile recuperare l'indirizzo email del locatore del mezzo."))
                        if mail_locatore:
                            break
                else:
                    # _logger.info("MEZZO DI PROPRIETA'")
                    # Se il mezzo appartiene ad un'azienda interna invio la mail all'assicurazione
                    # Controllo che il mezzo abbia un contratto di proprieta` attivo
                    contracts_property = self.env['fleet.vehicle.log.contract'].search_read(
                        [('vehicle_id', '=', vehicle['id']), ('cost_subtype_id', '=', 86)], order='id desc', limit=1)
                    if not contracts_property:
                        raise ValidationError(_("Non è stato possibile recuperare un contratto di proprieta` attivo."))
                    else:
                        _logger.info(f"Stampo contracts_property {contracts_property}")
                    # Cerco il contratto assicurativo attivo con type 13
                    contracts_assurance = self.env['fleet.vehicle.log.contract'].search_read(
                        [('vehicle_id', '=', vehicle['id']), ('cost_subtype_id', '=', 13)], order='id desc', limit=1)

                    if not contracts_assurance:
                        raise ValidationError(_("Non ho trovato assicurazioni attive."))

                    # recupero tutti gli indirizza mail associati al partner dell'assicurazione
                    for contract in contracts_assurance:
                        _logger.info(contract['insurer_id'][0])
                        _logger.info(contract['locator_location'])
                        if contract['insurer_id'] != False:
                            # _logger.info(f"STAMPO contract['insurer_id'] {contract['insurer_id']}")
                            is_insurer = self.env['res.partner'].search_read([('id', '=', contract['insurer_id'][0])],
                                                                             ['email'])
                            if is_insurer != []:
                                email_to_assurance = is_insurer[0]['email']
                                # _logger.info(f"STAMPO IL VALORE DELLA MAIL ASSICURAZIONE {email_to_assurance}")
                                if email_to_assurance == False:
                                    raise ValidationError(_("Non esiste alcuna mail associata all'assicurazione."))
                            else:
                                raise ValidationError(
                                    _("Non è stato possibile recuperare l'indirizzo email dell'assicurazione del mezzo."))
                        else:
                            raise ValidationError(_("Non è stato possibile recuperare l'assicurazione del mezzo."))
                    if email_to_assurance:
                        body_assurance = f"""<p>Buongiorno,<br />
                                            di seguito riepilogo sinistro</p><br /><p><b>Data/Ora: </b>{self.date.strftime('%d/%m/%Y %H:%M')}<br /><b>Autista: </b>{self.purchaser_id.name}<br /><b>Responsabilità: </b>{responsibility}<br /></p><p><b>Danni mezzo proprio:</b><ul>{list_damages}</ul></p><p><b>Note: </b>{self.notes}</p><p><b><U>In allegato la documentazione attestante il fatto</U></b></p><br /><br /><p>Futura</p>"""
                        # _logger.info(body_assurance)
                        mail_values = {
                            'subject': f'Sinistro rif.int. {str(self.id)} - assicurazione',
                            'email_from': 'catchall@futurasl.com',
                            'email_to': email_to_assurance,
                            'email_cc': 'catchall@futurasl.com',
                            'reply_to': 'catchall@futurasl.com',
                            'model': 'fleet.vehicle.log.services',
                            'res_id': self.id,
                            'body_html': body_assurance,
                            'attachment_ids': attach,  # Aggiungi l'allegato all'email
                        }

                        mail_assurance = self.env['mail.mail'].sudo().create(mail_values)
                        _logger.info(f"Creo la mail all'assicurazione perche il suo valore e' {email_to_assurance}")

                    # _logger.info("Mail inviata all'assicurazione")

            # Scrivo nel chatter cosa ha appena fatto l'utente
            str_foto = ""
            str_cai = ""
            str_denuncia = ""
            if is_foto_sinistro != []:
                str_foto = "<p>Foto del sinistro</p>"
            if is_cai != []:
                str_cai = "<p>CAI</p>"
            if is_denuncia != []:
                str_denuncia = "<p>Denuncia sinistro polizia</p>"

            partner_id = self.env['res.users'].browse(self.env.uid).partner_id.id
            # mail inviata al locatore
            # mail non inviata all'interinale e all'assicurazione
            if interinale == False and email_to != "" and email_to_assurance == "":
                mail_locatore.send()
                self.env['mail.message'].create(
                    {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                     'body': f"<p>Ho appena inviato la seguente mail al locatore del mezzo:</p><p>Segnalazione apertura sinistro</p>{str_foto}{str_cai}{str_denuncia}"})
            # mail inviata all'interinale
            # mail non inviata al locatore e all'assicurazione
            elif interinale != False and email_to == "" and email_to_assurance == "":
                if self.responsibility not in ['unnknown', 'third']:
                    mail_interinale.send()
                    self.env['mail.message'].create(
                        {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                         'body': f"<p>Ho appena inviato la seguente mail all'interinale:</p><p>Segnalazione apertura sinistro</p>{str_foto}{str_cai}{str_denuncia}"})
            # mail inviata all'interinale e al locatore
            # mail non inviata all'assicurazione
            elif interinale != False and email_to != "" and email_to_assurance == "":
                mail_locatore.send()
                text = ""
                if self.responsibility not in ['unnknown', 'third']:
                    mail_interinale.send()
                    text = "all'interinale e"
                self.env['mail.message'].create(
                    {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                     'body': f"<p>Ho appena inviato la seguente mail {text} al locatore del mezzo:</p><p>Segnalazione apertura sinistro</p>{str_foto}{str_cai}{str_denuncia}"})
            # mail inviata all'assicurazione
            # mail non inviata all'interinale e al locatore
            elif interinale == False and email_to == "" and email_to_assurance != "":
                mail_assurance.send()
                self.env['mail.message'].create(
                    {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                     'body': f"<p>Ho appena inviato la seguente mail all'assicuratore:</p><p>Segnalazione apertura sinistro</p>{str_foto}{str_cai}{str_denuncia}"})
            # mail inviata all'interinale e all'assicurazione
            # mail non inviata al locatore
            elif interinale != False and email_to == "" and email_to_assurance != "":
                text = ""
                if self.responsibility not in ['unnknown', 'third']:
                    mail_interinale.send()
                    text = "all'interinale e"
                mail_assurance.send()
                self.env['mail.message'].create(
                    {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                     'body': f"<p>Ho appena inviato la seguente mail {text} all'assicuratore:</p><p>Segnalazione apertura sinistro</p>{str_foto}{str_cai}{str_denuncia}"})
            # nessuna mail inviata
            else:
                # _logger.info(
                #     f"STAMPO I VALORI DI interinale {interinale}, email_to {email_to} E email_to_assurance {email_to_assurance}")
                raise ValidationError(_("Non è stata inviata alcuna segnalazione."))
            if is_employee_external:
                self.env['mail.message'].create(
                    {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                     'body': f"<p>Essendo un dipendente esterno, bisogna gestirlo manualmente.</p>"})
            self[0].state = 'reported'

            # Una volta cambiato lo stato in "Segnalato" devo cancellare eventuali attività
            self.check_open_activity()

    # Invio il totale dell'addebito e le relative informazioni all'interinale
    # Creo un eventuale contestazione
    # Passo allo stato "Processed"
    def to_processed(self):
        # Controllo se il dipendente e` un esterno
        is_employee_external = self.purchaser_id.is_esterno
        have_deduction = self.env['deduction.deduction'].search_read([('fleet_vehicle_log_service_id', '=', self.id)])
        if have_deduction != []:
            document = self.check_documents()
            if document == True:
                # Recupero i rop che dovranno ricevere anche loro la mail
                # _logger.info("AAAAAAAAAAAAA")
                _logger.info(self.trip_id['id'])
                organization_id = self.env['gtms.trip'].search_read([('id', '=', self.trip_id['id'])],
                                                                    ['organization_id'])
                rop_ids = self.env['helpdesk.team'].sudo().search_read(
                    [('organization_id', '=', organization_id[0]['organization_id'][1])], ['message_partner_ids'])

                # Visto che tutti i documenti obbligatori sono stati allegati è possibile procedere con la segnalazione del sinistro al fornitore dei mezzi e ad eventuale interinale

                # Recupero l'importo che dovrà essere addebitato
                deduction_ids = self.deduction_ids.ids
                total_import = 0.0
                for deduction_id in deduction_ids:
                    total_import += self.env['deduction.deduction'].search(
                        [('id', '=', deduction_id), ('date', '!=', False)]).deduction_value
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
                attachment_id = \
                self.env['documents.document'].search_read([('tag_ids', '=', 43), ('service_id.id', '=', self.id)],
                                                           ['attachment_id'])[0]['attachment_id'][0]
                attachment_ids = self.env['documents.document'].search_read(
                    [('tag_ids', 'in', [43, 59, 57, 58]), ('service_id.id', '=', self.id)], [
                        'attachment_id'])  # Gli allegati da inviare sono: Modulo dichiarazione danni, Foto sinistro, CAI, Denuncia polizia
                attach = []
                for attachments in attachment_ids:
                    _logger.info(attachments)
                    attach.append((4, attachments['attachment_id'][0]))
                # attach = self.env['documents.document'].search_read([('tag_ids', '=', 43),('service_id.id', '=', self.id)], ['attachment_id'])[0]
                # _logger.info("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
                _logger.info(attachment_id)
                _logger.info(attach)
                # _logger.info("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

                # Recupero lista danni
                damages = self.env['reparation.reparation'].search_read(
                    [('fleet_vehicle_log_service_id', '=', self.id)])
                list_damages = ""
                for damage in damages:
                    _logger.info(damage['damage_type_id'][1])
                    list_damages += "<li>" + str(damage['damage_type_id'][1]) + "</li>"
                # Recupero l'interinale
                interinale = self.check_interinale_a()
                # Se è interinale e la responsabilità non è "Sconosciuta" o di "Terzi" procedo con l'invio della comunicazione
                if not is_employee_external and interinale != "" and self.responsibility not in ['unnknown', 'third']:
                    # Siccome il dipendente è attualmente interinale, bisognerà avvisare del sinistro l'interinale.
                    body_interinale = f"""<p>Alla cortese attenzione del Responsabile Risorse Umane,<br></br>di seguito riepilogo sinistro: <br></br><br></br><b>Data/Ora:</b> {self.date.strftime('%d/%m/%Y %H:%M')} <br></br><b>Veicolo:</b> {self.vehicle_id.license_plate}<br></br><b>Autista:</b> {self.purchaser_id.name}<br></br><b>Responsabilità:</b> {responsibility}<br></br><br></br><br></br><p><b>Danni mezzo proprio ed eventuali parti coinvolte:</b><ul>{list_damages}</ul></p>
                <p><U>Potete procedere alla trattenuta della franchigia pari a € {importo_formattato},eventuali rateizzazioni verranno comunicate come di consueto a mezzo Timesheet</U></p>
                <p><b>Vi ricordo come da regolamento aziendale firmato dalla risorsa che le trattenute potranno avvenire anche in deroga ai limiti legali imposti.</b></p><br><p>In allegato la documentazione attestante il fatto.</p><br></br><p>Estratto regolamento aziendale: "Avuto riguardo alla non operabilità dei presupposti legali ex art. 1246 c.c. e art. 545 c.p.c. presupponenti ai fini di una compensazione tecnica, l’autonomia dei rapporti cui si riferiscono i contrapposti crediti delle parti e non operanti quando essi nascano dal medesimo rapporto, comportando soltanto un mero accertamento contabile di dare e avere, la relativa compensazione “tecnica” potrà avvenire anche in deroga ai limiti legali imposti e, dunque, anche in un’unica soluzione ed a prescindere dalle trattenute in corso per eventuali cessioni di credito e/o di pignoramento dello stipendio.</p><br></br><br></br><p>Futura</p>"""
                    _logger.info(body_interinale)
                    mail_values = {
                        'subject': f'Sinistro rif.int. {str(self.id)}',
                        'email_from': 'catchall@futurasl.com',
                        'email_to': interinale,
                        'email_cc': 'catchall@futurasl.com',
                        'reply_to': 'catchall@futurasl.com',
                        'model': 'fleet.vehicle.log.services',
                        'res_id': self.id,
                        'body_html': body_interinale,
                        'attachment_ids': attach,  # Aggiungi l'allegato all'email
                    }

                    mail = self.env['mail.mail'].sudo().create(mail_values)
                    mail.send()
                    partner_id = self.env['res.users'].browse(self.env.uid).partner_id.id
                    self.env['mail.message'].create(
                        {'model': 'fleet.vehicle.log.services', 'res_id': self.id, 'author_id': partner_id,
                         'body': f"<p>Ho appena inviato la seguente mail all'interinale:</p><p>Comunicazione totale degli importi da trattenere</p>"})

            ###########
            ###########
            # VEDERE CON ROBY SE DOBBIAMO APRIRE SUBITO UNA CONTESTAZIONE AL DIPENDENTE (SE INTERNO)
            # if interinale == "" and self.responsibility not in ['unnknown', 'third']:

            # Passo allo stato "Processed"
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
        self.check_interinale_a()

    # Creo un metodo per aprire il wizard per decidere come mai non e` addebitabile
    def open_charged_wizard(self):
        # Creo un record del wizard
        # Apro il wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'fleet.vehicle.log.services.charged.wizard',
            'name': 'Motivazione del mancato addebito',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': {'default_text': '', 'default_anomaly_id': self.id}
        }

    def set_to_be_charged(self):
        self.to_be_charged = 'yes'

    def reset_to_be_charge(self):
        self.to_be_charged = False
        self.motivation_of_charge = ''

##################
#    DA FARE     #
##################
# - Mettere il campo locator_location visibile solo bnei contratti di noleggio e noleggio scorta
# - Recuperare la sede del locatore per poter inviare la mai agli indirizzi corretti.
