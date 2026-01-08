import asyncio
import requests
import httpx
import pandas as pd


class EfdQueryClient:
    """
    Query client for accessing Summit EFD (InfluxDB telemetry system).

    Parameters
    ----------
    site : str
        Observatory site name (e.g., "summit").
    db_name : str
        Name of the telemetry database (e.g., "efd").
    """
    def __init__(self, site: str = "summit", db_name: str = "efd"):
        site = site + "_efd"
        creds_url = f"https://roundtable.lsst.codes/segwarides/creds/{site}"
        credentials = httpx.get(creds_url).json()

        self.auth = (credentials["username"], credentials["password"])
        self.url = "https://" + credentials["host"] + credentials["path"] + "query"
        self.db_name = db_name

    def query(self, query: str) -> pd.DataFrame:
        """
        Execute a query on the EFD database.

        Parameters
        ----------
        query : str
            InfluxDB query.

        Returns
        -------
        pandas.DataFrame
        """
        params = {"db": self.db_name, "q": query}
        response = httpx.get(self.url, auth=self.auth, params=params)
        response.raise_for_status()

        result = response.json()["results"][0]
        if "series" not in result:
            return pd.DataFrame([])

        series = result["series"][0]
        return pd.DataFrame(series["values"], columns=series["columns"])


AUTH_URL = "http://cmms-402.cp.lsst.org:8080/openmaint/services/rest/v3/sessions?scope=service&returnId=true"
USERNAME = "admin"
PASSWORD = "admin"

URL_PM_CONFIG = "http://cmms-402.cp.lsst.org:8080/openmaint/services/rest/v3/classes/PrevMaintConfig/cards/{config_id}"
URL_PM_CREATE = "http://cmms-402.cp.lsst.org:8080/openmaint/services/rest/v3/processes/PreventiveMaint/instances"
URL_PM_ACTIVITIES = "http://cmms-402.cp.lsst.org:8080/openmaint/services/rest/v3/processes/PreventiveMaint/instances/{pm_id}/activities"
URL_PM_ADVANCE = "http://cmms-402.cp.lsst.org:8080/openmaint/services/rest/v3/processes/PreventiveMaint/instances/{pm_id}"

SITE = "summit"
DB_NAME = "efd"

MEASUREMENT = "lsst.sal.HVAC.dynaleneP05"
FIELD = "dynCH01supFS01"

THRESHOLD = 40.0
CONFIG_ID = "434357"
CHECK_INTERVAL = 60

LAST_PM_ID = None


def authenticate() -> str | None:
    payload = {"username": USERNAME, "password": PASSWORD}
    response = requests.post(AUTH_URL, json=payload, verify=False, timeout=10)
    token = response.json().get("data", {}).get("_id")
    if token:
        print("[AUTH] Token acquired.")
        return token
    print("[AUTH] Authentication failed:", response.text)
    return None


def read_telemetry(client: EfdQueryClient) -> float | None:
    """
    Retrieve the most recent telemetry value from EFD.
    If the query fails or times out, return None.

    Parameters
    ----------
    client : EfdQueryClient

    Returns
    -------
    float or None
    """
    query = (
        f'SELECT "{FIELD}" FROM "{MEASUREMENT}" '
        f"WHERE time > now() - 5m ORDER BY time DESC LIMIT 1"
    )

    try:
        df = client.query(query)
    except Exception as exc:
        print(f"[EFD] Query timeout or network error. Skipping cycle. Details: {exc}")
        return None

    if df.empty:
        print("[EFD] No data available for this interval.")
        return None

    return float(df.iloc[0][FIELD])



async def load_pm_configuration(client: httpx.AsyncClient, token: str) -> dict:
    headers = {"CMDBuild-Authorization": token}
    response = await client.get(URL_PM_CONFIG.format(config_id=CONFIG_ID), headers=headers, timeout=10)
    return response.json().get("data", {})


async def get_pm_status(client: httpx.AsyncClient, token: str, pm_id: str) -> str | None:
    headers = {"CMDBuild-Authorization": token}
    response = await client.get(URL_PM_CREATE, headers=headers, timeout=10)

    for pm in response.json().get("data", []):
        if pm.get("_id") == pm_id:
            status = pm.get("_status_description")
            return status.lower() if status else None
    return None


async def create_pm_instance(client: httpx.AsyncClient, token: str) -> str | None:
    config = await load_pm_configuration(client, token)
    if not config:
        print("[PM] PM configuration unavailable.")
        return None

    payload = {
        "Description": config.get("Description"),
        "Site": config.get("Site"),
        "Action": config.get("Action"),
        "CISubset": config.get("CISubset"),
        "Team": config.get("Team"),
        "Priority": config.get("Priority"),
        "EstimatedDuration": config.get("EstimatedDuration"),
        "Notes": config.get("Notes"),
        "ActivityType": config.get("ActivityType"),
        "maintConf": CONFIG_ID,
        "PrevMaintConfig": CONFIG_ID,
        "ShortDescr": config.get("Description"),
    }

    headers = {"CMDBuild-Authorization": token, "Content-Type": "application/json"}
    response = await client.post(URL_PM_CREATE, headers=headers, json=payload, timeout=10)
    return response.json().get("data", {}).get("_id")


async def advance_pm_instance(client: httpx.AsyncClient, token: str, pm_id: str) -> None:
    headers = {"CMDBuild-Authorization": token, "Content-Type": "application/json"}
    activities = await client.get(URL_PM_ACTIVITIES.format(pm_id=pm_id), headers=headers, timeout=10)
    activity_id = activities.json()["data"][0]["_id"]
    payload = {"_activity": activity_id, "_type": "PreventiveMaint", "_advance": True, "status": "acceptance"}
    await client.put(URL_PM_ADVANCE.format(pm_id=pm_id), headers=headers, json=payload, timeout=10)
    print(f"[PM] PM {pm_id} advanced.")


async def main():
    global LAST_PM_ID

    token = authenticate()
    if not token:
        return

    efd_client = EfdQueryClient(site=SITE, db_name=DB_NAME)

    async with httpx.AsyncClient(verify=False) as client:
        while True:
            value = read_telemetry(efd_client)

            if value is not None:
                print(f"[EFD] Value: {value}")

                if value < THRESHOLD:

                    if LAST_PM_ID is not None:
                        status = await get_pm_status(client, token, LAST_PM_ID)

                        if status and status not in ("closed", "completed", "aborted"):
                            print(f"[PM] Waiting. Current PM {LAST_PM_ID} is still active ({status}).")
                            await asyncio.sleep(CHECK_INTERVAL)
                            continue

                    pm_id = await create_pm_instance(client, token)

                    if pm_id:
                        LAST_PM_ID = pm_id
                        await advance_pm_instance(client, token, pm_id)

            await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

