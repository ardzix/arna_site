import json
from urllib.request import Request, urlopen

with urlopen(Request('http://127.0.0.1:8001/health/ready', headers={'Host': 'site.arnatech.id'}), timeout=4) as response:
    assert response.status == 200 and json.load(response)['status'] == 'ok'
