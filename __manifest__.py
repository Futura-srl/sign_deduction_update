{
    'name': 'sign deduction update',
    'version': '16',
    'author': "Luca Cocozza",
    'application': True,
    'description': "Modulo per generare il documento relativo al danno / multa da far firmare al dipendente.",
    'depends': ['fleet_deduction_sign'],
    'data': [
        'data/ir.model.access.csv',
        # # Caricamento delle view,
        'view/fleet_vehicle_log_services.xml',
        'view/fleet_vehicle_log_contract.xml',
        'view/helpdesk_team_view.xml',
        'view/fleet_vehicle_renter_view.xml',
    ],
}
