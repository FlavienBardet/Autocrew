
# filename: autocrew.py
#####################################################################################################################
AUTOCREW_VERSION = "2.1.4"

# Please do not edit this file directly
# Please modify the config file, "config.ini"
# If you experience any errors, please upload the complete log file, "autocrew.log", along with your issue on GitHub:
# https://github.com/yanniedog/autocrew/issues/new 
#####################################################################################################################


import argparse
import configparser
import copy
import csv
import io
import json
import logging
import os
import re
import requests
import shutil
import subprocess
import sys
import tiktoken
import time

from core import AutoCrew
from datetime import datetime
from packaging import version
from typing import Any, Dict, List

from crewai import Agent, Crew, Process, Task
from langchain_community.llms import Ollama
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from openai import OpenAI

GREEK_ALPHABETS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
                       "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon"]

def initialize_logging(verbose=False, message=None):
    log_file = os.path.join(os.getcwd(), 'autocrew.log')
    config_file = os.path.join(os.getcwd(), 'config.ini')
    config = configparser.ConfigParser()
    config.read(config_file)

    console_logging_level = logging.INFO

    if not verbose and config.has_option('MISCELLANEOUS', 'on_screen_logging_level'):
        config_level = config.get('MISCELLANEOUS', 'on_screen_logging_level').upper()
        console_logging_level = getattr(logging, config_level, logging.INFO)

    if verbose:
        console_logging_level = logging.DEBUG

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        logger.handlers.clear()
        
    logging.getLogger("httpcore").setLevel(logging.DEBUG)
    
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - (%(filename)s,%(funcName)s,%(lineno)d) - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_logging_level)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    if message:
        logger.info(message)
        
        
def log_command_line_arguments():
    logging.info(f"Command-line arguments: {' '.join(sys.argv[1:])}")
    
    
    
def install_dependencies():
    requirements_file = 'requirements.txt'
    if not os.path.exists(requirements_file):
        raise FileNotFoundError(f"{requirements_file} not found in the current working directory.")

    pip_executable = shutil.which('pip') or shutil.which('pip3')
    if not pip_executable:
        raise EnvironmentError("pip is not available on the system.")

    logging.info("Installing dependencies...")

    result = subprocess.run([pip_executable, 'install', '-r', requirements_file], capture_output=True, text=True)

    if result.returncode != 0:
        logging.error("Error occurred while installing dependencies:")
        logging.error(result.stdout)
        logging.error(result.stderr)

        raise RuntimeError("Failed to install dependencies.")
    else:
        print("Dependencies installed successfully.")

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

def positive_int(value):
        try:
            ivalue = int(value)
            if ivalue <= 0:
                raise argparse.ArgumentTypeError(f"{value} is an invalid positive int value")
            return ivalue
        except ValueError:
            print("Please specify the total number of alternative scripts to generate: ")
            while True:
                try:
                    return int(input())
                except ValueError:
                    print("Invalid input. Please enter a valid number.")             

def check_latest_version():
    try:
        response = requests.get('https://api.github.com/repos/yanniedog/autocrew/releases/latest')
        response.raise_for_status()
        latest_release = response.json()
        latest_version = latest_release['tag_name']

        if version.parse(latest_version) > version.parse(AUTOCREW_VERSION):
            return f"An updated version of AutoCrew is available: {latest_version}"
        else:
            return "You are running the latest version of AutoCrew."
    except Exception as e:
        return f"Error checking for the latest version: {e}"


def upgrade_autocrew(latest_version):
    backup_dir = '.backup'
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    logfile_path = 'autocrew.log'
    logfile_backup_name = f'autocrew-upgrade-logfile_(v-{AUTOCREW_VERSION}--to--v-{latest_version}).log'
    logfile_backup_path = os.path.join(backup_dir, logfile_backup_name)
    if os.path.exists(logfile_path):
        shutil.copyfile(logfile_path, logfile_backup_path)
        logging.info(f"Backing up the current logfile to {logfile_backup_path}...")

    config_backup_path = os.path.join(backup_dir, 'config_backup.ini')
    shutil.copyfile('config.ini', config_backup_path)
    logging.info("Backing up the current config.ini file...")

    update_dir = 'autocrew_update'
    if os.path.exists(update_dir):
        shutil.rmtree(update_dir)
    
    logging.info("Cloning the latest version from GitHub...")
    subprocess.run(['git', 'clone', 'https://github.com/yanniedog/autocrew.git', update_dir])

    for filename in os.listdir(update_dir):
        source_path = os.path.join(update_dir, filename)
        if os.path.isfile(source_path) and filename != 'config.ini':
            shutil.copyfile(source_path, filename)
            logging.info(f"Copied {filename} to the current directory.")

    logging.info("Updating the config.ini file with your previous settings...")
    config = configparser.ConfigParser()
    config.read(os.path.join(update_dir, 'config.ini'))
    config_backup = configparser.ConfigParser()
    config_backup.read(config_backup_path)
    for section in config_backup.sections():
        if not config.has_section(section):
            config.add_section(section)  
        for key, value in config_backup.items(section):
            config.set(section, key, value)
    with open('config.ini', 'w') as configfile:
        config.write(configfile)

    shutil.rmtree(update_dir)
    logging.info("Cleaned up the update directory.")

    logging.info(f"Upgrade successful. AutoCrew has been updated from version {AUTOCREW_VERSION} to version {latest_version}.")
    print(f"Upgrade successful. AutoCrew has been updated from version {AUTOCREW_VERSION} to version {latest_version}.")
    sys.exit(0)
    
def log_command_line_arguments():
    logging.info(f"Command-line arguments: {' '.join(sys.argv[1:])}")

def main():
    parser = argparse.ArgumentParser(description='CrewAI Autocrew Script', add_help=False)
    parser.add_argument('-v', '--verbose', action='store_true', help='Provide additional details during execution')
    parser.add_argument('-u', '--upgrade', action='store_true', help='Upgrade to the latest version of AutoCrew')
    parser.add_argument('-h', '-?', '--help', action='store_true', help='Show this help message and exit')
    parser.add_argument('overall_goal', nargs='?', type=str, help='The overall goal for the crew')
    parser.add_argument('-r', '--rank', action='store_true', help='Rank the generated crews if multiple scripts are created')
    parser.add_argument('-a', '--auto_run', action='store_true', help='Automatically run the scripts after generation')
    parser.add_argument('-m', '--multiple', type=positive_int, help='Generate multiple alternative scripts')
    args, unknown_args = parser.parse_known_args()

    # Initialize logging first
    initialize_logging(verbose=args.verbose)
    # Then log the command-line arguments
    log_command_line_arguments()

    # Global exception handling
    sys.excepthook = handle_exception

    # Check for the latest version
    version_message = check_latest_version()
    startup_message = (f"\nAutoCrew version: {AUTOCREW_VERSION}\n" +
                       f"{version_message}\n\n" +
                       "Use the -? or -h command line options to display help information.\n" +
                       "Settings can be modified within \"config.ini\". Scripts are saved in the \"scripts\" subdirectory.\n" +
                       "If you experience any errors, please create an issue on Github and attach \"autocrew.log\":\n" +
                       "https://github.com/yanniedog/autocrew/issues/new\n")
    logging.info(startup_message)

    if args.upgrade or args.help:
        if unknown_args:
            parser.print_usage()
            logging.error("Error: The '-u/--upgrade' and '-h/-?/--help' options cannot be used with other arguments.")
            sys.exit(1)
        elif args.upgrade:
            if version.parse(version_message) > version.parse(AUTOCREW_VERSION):
                upgrade_autocrew(version_message)
            else:
                logging.info("No new version available or you are already running the latest version.")
            sys.exit(0)
        elif args.help:
            parser.print_help()
            sys.exit(0)

    autocrew = AutoCrew()
    autocrew.log_config_with_redacted_api_keys()

    # Ensure overall goal is set
    if args.overall_goal is None:
        args.overall_goal = input("Please set the overall goal for your crew: ")

    try:
        # Independent Ranking Process
        if args.rank:
            logging.info("Ranking process initiated.")
            csv_file_paths = autocrew.get_existing_scripts(args.overall_goal)
            if not csv_file_paths:
                logging.error("No existing scripts found to rank.")
                sys.exit(1)
            ranked_crews, overall_summary = autocrew.rank_crews(csv_file_paths, args.overall_goal, args.verbose)
            logging.debug(f"Ranking prompt:\n{overall_summary}\n")
            autocrew.save_ranking_output(ranked_crews, args.overall_goal)
            logging.info("Ranking process completed.")
            sys.exit(0)  # Exit after ranking

        # Script Generation Process
        csv_file_paths = []
        if args.multiple and args.multiple > 1:
            logging.info(f"Generating {args.multiple} alternative scripts...")
            csv_file_paths = autocrew.generate_scripts(args.overall_goal, args.multiple)
        else:
            single_script_path = autocrew.run(args.overall_goal, None, args.auto_run, args.verbose)
            csv_file_paths.append(single_script_path)

        # Auto-run Scripts
        if args.auto_run:
            for path in csv_file_paths:
                script_path = path.replace('.csv', '.py')
                subprocess.run([sys.executable, script_path])
    except Exception as e:
        logging.exception("An error occurred during script execution.")
        sys.exit(1)

if __name__ == '__main__':
    main()