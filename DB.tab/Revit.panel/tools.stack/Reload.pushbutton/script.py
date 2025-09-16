# -*- coding=utf-8 -*-
#pylint: disable=import-error,invalid-name,broad-except
from pyrevit import EXEC_PARAMS
from pyrevit import script
from pyrevit import forms
from pyrevit.userconfig import user_config
from pyrevit.loader import sessionmgr
from pyrevit.loader import sessioninfo
import subprocess
import traceback
import sys

stdout = sys.stdout

# if not "main_dev" in __file__:
#     try:
#         sourcePath = user_config.get_section("db.extension").get_option("sourcePath")
#         update = sourcePath+"\\update.ps1"
#         p = subprocess.call(["powershell.exe", "-ExecutionPolicy", "remotesigned", "-File", update])
#     except:
#         print(str(traceback.format_exc()))
#         print("\n\nFehler beim Updaten. Ist der folgende Netzwerkpfad erreichbar?")
#         print(update)

if EXEC_PARAMS.config_mode:
    core = user_config.get_section("core")
    loadbeta = core.get_option("loadbeta" , False)
    core.set_option("loadbeta", not loadbeta)
    pass

logger = script.get_logger()
results = script.get_results()

# re-load pyrevit session.
logger.info('Reloading....')
sessionmgr.reload_pyrevit()

results.newsession = sessioninfo.get_session_uuid()
