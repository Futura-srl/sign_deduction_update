{
    'name': 'sign deduction update',
    'version': '17.2',
    'author': "Luca Cocozza",
    'application': True,
    'description': "Modulo per generare il documento relativo al danno / multa da far firmare al dipendente.",
    'depends': ['fleet_deduction_sign', 'fleet_service_with_deduction', 'fleet', 'hr', 'stesi_fleet_documents', 'dipendenti'],
    'data': [
        'security/ir.model.access.csv',
        # # Caricamento delle view,
        'view/fleet_vehicle_log_services.xml',
        'view/fleet_vehicle_log_contract.xml',
        'view/helpdesk_team_view.xml',
        'view/fleet_vehicle_renter_view.xml',
        'view/deduction_deduction.xml',
        'wizard/fleet_vehicle_log_services_charged_wizard.xml',
    ],
    'external_dependencies': {
    'python': ['python-docx', 'docx2pdf', 'pdfkit', 'pydocx'],
},
}
