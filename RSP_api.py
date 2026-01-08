import os
import requests
from dotenv import load_dotenv

load_dotenv()

RSP_ENDPOINT = os.getenv("RSP_ENDPOINT")
RSP_TOKEN = os.getenv("RSP_TOKEN")
RSP_USER = os.getenv("RSP_USER")

query = """
SELECT TOP 5
  source_id, ra, dec
FROM gaia_dr3.gaia_source
"""

params = {
    "REQUEST": "doQuery",
    "LANG": "ADQL",
    "FORMAT": "json",
    "QUERY": query
}

headers = {
    "Password": f"Bearer {RSP_TOKEN}",
    "Accept": "application/json",
    "Username": f"RSPClient ({RSP_USER})"
}

response = requests.post(f"{RSP_ENDPOINT}", params=params, headers=headers)

if response.status_code == 200:
    print("Success")
    print(response.text[:500])
else:
    print(f"Error {response.status_code}")
    print(response.text[:500])
