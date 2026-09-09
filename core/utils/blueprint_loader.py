# utils/blueprint_loader.py

import json
from pathlib import Path
from django.conf import settings


def load_workflow_blueprint():
    blueprint_path = (
        Path(settings.BASE_DIR)
        / 'data'
        / 'workflow_blueprint.json'
    )
    
    with open(blueprint_path, 'r', encoding='utf-8') as file:
        return json.load(file)