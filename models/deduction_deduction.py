from odoo import models, fields, api


class DeductionDeduction(models.Model):
    _inherit = 'deduction.deduction'
    
    processed = fields.Boolean()
    processed_by = fields.Char(readonly=True)
    processed_on = fields.Datetime(readonly=True)
    invoice = fields.Char()
    on_pwork = fields.Boolean(default=False, help="Check this box if the deduction is uploaded to Pwork.")
    pwork_error = fields.Text(string='Pwork Error', help="Error message if the upload to Pwork fails.")
    
    @api.onchange('processed')
    def _deduction_processed(self):
        if self.processed:
            self.processed_by = self.env.user.name
            self.processed_on = fields.Datetime.now()
        else:
            self.processed_by = False
            self.processed_on = False


    def action_upload_to_pwork(self):
        for record in self:
            if not record.invoice:
                record.pwork_error = "Invoice number is required to upload to Pwork."
                return False



            # Simulate the upload process
            try:
                # Here you would implement the actual upload logic to Pwork
                # For now, we just simulate a successful upload
                record.on_pwork = True
                record.pwork_error = False
            except Exception as e:
                record.pwork_error = str(e)
                return False

        return True

    def upload_voce_pwork(self, token, cod_azienda, codice_fiscale, data, voce, value, qta):
        data_xml = """
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
                                <CodiceFiscale>{}</CodiceFiscale>
                                <Data>{}</Data>
                                <Voce>{}</Voce>
                                <Value>{}</Value>
                                <Qta>{}</Qta>
                            </RequestTMVociEx>
                        </Params>
                        <ReturnType>FormatJson</ReturnType>
                    </setTM_Voce>
                </soap12:Body>
            </soap12:Envelope>'''.format(token, cod_azienda, codice_fiscale, data, voce, value, qta))

                """