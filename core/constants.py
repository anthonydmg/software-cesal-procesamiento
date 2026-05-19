

ETAPAS_FENOLOGICAS = ["Inicio de brote", "Pre-floración", "Floración", 
                        "Cuajado", "Maduración", "Cosecha"]
                            
THRESH_STAGES_DEFAULT = {"Inicio de brote": 3.0,
                         "Pre-floración": 2.8,
                         "Floración": 2.6, 
                         "Cuajado": 2.0, 
                         "Maduración": 1.8, 
                         "Cosecha": 2.4
                        }

TIPOS_SUELOS = ["Arenoso", "Franco", "Arcilloso", 
                            "Limoso", "Pedregoso"]

TIPOS_RIEGOS = ["Gravedad", "Aspersión", "Goteo", 
                            "Microaspersión"]

UNCERTANTY_VALUE = 0.539

DEFAULT_PROCESS_CONFIG = {
    "target_resolution_option" : 0,
    "tresh_stages": THRESH_STAGES_DEFAULT
}

