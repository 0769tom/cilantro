"""Module for initializing settings related to the built-in Cilantro logger
Functions:
-get_logger"""

import logging, coloredlogs
import os, sys

VALID_LVLS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
_LOG_LVL = os.getenv('LOG_LEVEL', 'DEBUG')
assert _LOG_LVL in VALID_LVLS, "Log level {} not in valid levels {}".format(_LOG_LVL, VALID_LVLS)
_LOG_LVL = getattr(logging, _LOG_LVL)

def get_main_log_path():
    from cilantro import logger

    root = logger.__file__  # resolves to '/Users/davishaba/Developer/cilantro/cilantro/logger/__init__.py'
    log_path = '/'.join(root.split('/')[:-3]) + '/logs/cilantro.log'

    # Create log directory if it does not exist
    log_dir = os.path.dirname(log_path)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    return log_path

format = '%(asctime)s.%(msecs)03d %(name)s[%(process)d][%(processName)s] %(levelname)-2s %(message)s'

coloredlogs.DEFAULT_LEVEL_STYLES = {
    'critical':{ 'color':'white', 'bold':True, 'background': 'red' },
    'debug':{ 'color':'green' },
    'error':{ 'color':'red' },
    'info':{ 'color':'white' },
    'notice':{ 'color':'magenta' },
    'spam':{ 'color':'green', 'faint':True },
    'success':{ 'color':'green', 'bold':True },
    'verbose':{ 'color':'blue' },
    'warning':{ 'color':'yellow' }
}
coloredlogs.DEFAULT_FIELD_STYLES = {
    'asctime': {'color': 'green'},
    'hostname': {'color': 'magenta'},
    'levelname': {'color': 'black', 'bright': True},
    'name': {'color': 'blue'},
    'programname': {'color': 'cyan'}
}

class LoggerWriter:
    def __init__(self, level):
        self.level = level
    def write(self, message):
        if message != '\n':
            self.level(message)
    def flush(self):
        return

class ColoredFileHandler(logging.FileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFormatter(
            coloredlogs.ColoredFormatter(format)
        )

class ColoredStreamHandler(logging.StreamHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFormatter(
            coloredlogs.ColoredFormatter(format)
        )

def get_logger(name=''):

    filedir = "logs/{}".format(os.getenv('TEST_NAME', 'test'))
    filename = "{}/{}.log".format(filedir, os.getenv('HOSTNAME', name))
    os.makedirs(filedir, exist_ok=True)

    filehandlers = [
        logging.FileHandler(get_main_log_path()),
        logging.FileHandler(filename),
        ColoredFileHandler('{}_color'.format(filename)),
        ColoredStreamHandler()
    ]
    logging.basicConfig(
        format=format,
        handlers=filehandlers,
        level=logging.DEBUG
    )

    log = logging.getLogger(name)
    log.setLevel(_LOG_LVL)

    # sys.stdout = LoggerWriter(log.debug)
    # sys.stderr = LoggerWriter(log.error)

    return log

def overwrite_logger_level(level):
    global _LOG_LVL
    _LOG_LVL = level

    for name in logging.Logger.manager.loggerDict.keys():
        log = logging.getLogger(name)
        log.setLevel(level)
