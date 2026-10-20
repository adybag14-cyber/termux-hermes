import json,sys
from pathlib import Path
events=[]
def audit(event,args):
 if event in ("socket.connect","socket.getaddrinfo","socket.connect_ex"):
  events.append(event)
  raise RuntimeError("Network forbidden during offline wheel install")
sys.addaudithook(audit)
import pip
from pip._internal.models.scheme import Scheme
from pip._internal.operations.install.wheel import install_wheel
spec=json.loads(Path(sys.argv[1]).read_bytes())
scheme=Scheme(**spec["scheme"])
for item in spec["wheels"]:
 install_wheel(item["name"],item["path"],scheme,req_description=item["name"]+" independently reviewed offline packaging fixture",pycompile=False,warn_script_location=False,requested=True)
Path(sys.argv[2]).write_text(json.dumps({"status":"passed","pip":pip.__version__,"method":"real pip install_wheel with explicit Android-style Scheme","resolution":False,"network_attempts":events,"pycompile":False,"wheels":spec["wheels"]},indent=2)+"\n",encoding="utf-8")
