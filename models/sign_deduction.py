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

_logger = logging.getLogger(__name__)
date_today = date.today()

class FleetVehicleLogServices(models.Model):
    _inherit = 'fleet.vehicle.log.services'

    
    
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

    
    def create_document_request_sign(self):
        template_id = self.add_template_for_sign()
        _logger.info(template_id)
        reference_name = str(self.id) + " " + str(self.service_type_id.name) + " " + str(self.description)
        self.env['sign.request'].create({
            'anomaly_id': self.id,
            'reference': reference_name,
            'request_item_ids': [(0, 0, {
                'partner_id': self.purchaser_id.id,
                'role_id': 3,
        })],
            'template_id': template_id,
        })
        sign_template = self.env['sign.template'].browse(template_id)  # Recupera il record con ID 13
        sign_template.write({'active': False})