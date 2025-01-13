



import os, stat, os.path
import shutil
import re
import time
import subprocess
import yaml
from natsort import natsorted
from datetime import datetime, timedelta
import logging
import os




log = logging.getLogger(__name__)

def convert_dict_to_strutex(dictionary):
    for key, value in dictionary.items():
        result_string = result_string + f"\n\t{key}:: {value}"
    return result_string

def main():
    logfile_path = '/var/run/zmirror/log.st'
    config_file_path = "/etc/zmirror/config.yml"
    parent_directory = os.path.dirname(logfile_path)
    os.makedirs(parent_directory, exist_ok = True)
    logging.basicConfig(filename=logfile_path, 
                        level=logging.INFO, 
                        format='%(asctime)s %(levelname)-8s %(message)s',    
                        datefmt='%Y-%m-%d %H:%M:%S')
    log.info("starting zmirror")
    all_env_vars = dict(os.environ)
    new_all_env_vars = dict()
    for key, value in all_env_vars.items():
        if key[0] != "_":
            new_all_env_vars[key] = value
    with open(config_file_path) as config_file:
        config_dict = yaml.safe_load(config_file)
    if config_dict["log-env"] == "yes":
        result_string = "env" + convert_dict_to_strutex(new_all_env_vars)
        log.info(f"environment variables: {result_string}")
    dm_crypts = config_dict["dm-crypts"]
    for name, dm_crypt in dm_crypts.items():
        type = dm_crypt["type"]
        key_file = dm_crypt["key-file"]
        if type == "partition":
            if "zfs" in dm_crypt:
                zfs = dm_crypt[zfs]
                pool = zfs["pool"]
                dev = zfs["dev"]
                wait_for_scrub_max = zfs["wait-for-scrub-max"]
                scrub_schedule = zfs["scrub-schedule"]
                if "on-scrubbed" in zfs:
                    on_scrubbed = zfs["on-scrubbed"]
                if "on_resilvered" in zfs:
                    on_resilvered = zfs["on_resilvered"]
            if "vgs" in dm_crypt:
                vgs = dm_crypt["vgs"]
        elif type == "disk":
            serial = dm_crypt["serial"]
        


    
if __name__ == "__main__":
    main()

