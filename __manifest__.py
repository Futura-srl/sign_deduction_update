{
    'name': 'sign deduction update',
    'version': '16',
    'author': "Luca Cocozza",
    'application': True,
    'description': "Modulo per generare il documento relativo al danno / multa da far firmare al dipendente.",
    'depends': ['fleet_deduction_sign'],
    'data': [
        # # Caricamento delle view,
        'view/fleet_vehicle_log_services.xml',
    ],
}
