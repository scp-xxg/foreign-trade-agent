import os,importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('team','extensions/foreign_trade/team.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
env=m.runtime_env(Path('/root/.foreign-trade-agent'),3001)
cmd=['/workspace/.venv/bin/hugagent-server','serve','--host','0.0.0.0','--port','3001','--no-browser']
os.execve(cmd[0],cmd,env)
