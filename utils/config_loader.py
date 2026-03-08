# File: utils/config_loader.py

import os 
import yaml


class ConfigLoader:

    def __init__(self, filename):

        # Project root.
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Configs directory.
        configs_dir = os.path.join(root_dir, "configs")

        # Full path to selected config file.
        self.path = os.path.join(configs_dir, filename)

    def load(self):

        with open(self.path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)