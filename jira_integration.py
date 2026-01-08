import os
import asyncio
import base64
from typing import Optional, Dict

import httpx
from dotenv import load_dotenv

load_dotenv()

AUTH_URL = os.getenv("AUTH_URL")
CMMS_USERNAME = os.getenv("CMMS_USERNAME")
CMMS_PASSWORD = os.getenv("CMMS_PASSWORD")
CMMS_ORDER_ENDPOINT = os.getenv("CMMS_ORDER_ENDPOINT")

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")
JIRA_ISSUE_TYPE_ID = os.getenv("JIRA_ISSUE_TYPE_ID")

POLL_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 10

# CMMS process status constants

PROCESS_STATUS_PLANNING = 277465
PROCESS_STATUS_ACCEPTANCE = 261328

PROCESS_STATUS_MAP = {
    277465: "Planning",
    261328: "Acceptance",
    1114923: "Handoff",
    261329: "Execution",
    266628: "Suspension",
    429375: "Review",
    429376: "Schedule",
}

# CMMS client functions

async def login_cmms(client: httpx.AsyncClient) -> str:
    """
    Authenticate against the CMMS REST API and retrieve a session token.

    Parameters
    ----------
    client : httpx.AsyncClient
        HTTP client used to perform the authentication request.

    Returns
    -------
    str
        CMMS authentication token.

    Raises
    ------
    RuntimeError
        If the authentication token is not present in the response.
    """
    payload = {
        "username": CMMS_USERNAME,
        "password": CMMS_PASSWORD,
    }

    response = await client.post(
        AUTH_URL,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    token = response.json().get("data", {}).get("_id")
    if not token:
        raise RuntimeError("CMMS authentication token not received")

    return token


async def fetch_order_process_status(
    client: httpx.AsyncClient,
    token: str,
) -> int:
    """
    Retrieve the current process status of a CMMS maintenance order.

    Parameters
    ----------
    client : httpx.AsyncClient
        HTTP client used to perform the request.
    token : str
        CMMS authentication token.

    Returns
    -------
    int
        Process status identifier.

    Raises
    ------
    RuntimeError
        If the ProcessStatus attribute is missing in the response.
    """
    headers = {"CMDBuild-Authorization": token}

    response = await client.get(
        CMMS_ORDER_ENDPOINT,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()

    try:
        return payload["data"]["ProcessStatus"]
    except KeyError as exc:
        raise RuntimeError(
            "ProcessStatus attribute not found in CMMS response"
        ) from exc


def resolve_process_status_name(process_status_id: int) -> str:
    """
    Resolve a human-readable name for a CMMS process status ID.

    Parameters
    ----------
    process_status_id : int
        CMMS process status identifier.

    Returns
    -------
    str
        Human-readable process status name.
    """
    return PROCESS_STATUS_MAP.get(process_status_id, "UNKNOWN")


def has_transitioned_to_acceptance(
    previous_status_id: Optional[int],
    current_status_id: int,
) -> bool:
    """
    Determine whether the workflow transitioned from Planning to Acceptance.

    Parameters
    ----------
    previous_status_id : Optional[int]
        Previously observed process status identifier.
    current_status_id : int
        Current process status identifier.

    Returns
    -------
    bool
        True if the transition Planning → Acceptance occurred.
    """
    return (
        previous_status_id == PROCESS_STATUS_PLANNING
        and current_status_id == PROCESS_STATUS_ACCEPTANCE
    )

# Jira functions

def _build_jira_auth_header() -> Dict[str, str]:
    """
    Build HTTP headers for Jira Cloud Basic authentication.

    Returns
    -------
    Dict[str, str]
        HTTP headers including Authorization and content type.
    """
    raw = f"{JIRA_EMAIL}:{JIRA_API_TOKEN}"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")

    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _build_jira_issue_payload() -> Dict:
    """
    Build the payload for Jira issue creation.

    Returns
    -------
    Dict
        Jira issue creation payload compliant with Atlassian
        Document Format (ADF).
    """
    return {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "issuetype": {"id": JIRA_ISSUE_TYPE_ID},
            "summary": "CMMS order moved to Acceptance",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Order in CMMS transitioned from "
                                    "Planning to Acceptance.\n\n"
                                    "Automated ticket created by integration."
                                ),
                            }
                        ],
                    }
                ],
            },
        }
    }


def create_jira_issue() -> None:
    """
    Create a Jira issue associated with a CMMS workflow transition.

    This function performs a best-effort attempt to create the issue.
    Jira API errors are logged but do not interrupt CMMS monitoring.
    """
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    payload = _build_jira_issue_payload()

    print("PHASE: Jira ticket creation")
    print("Sending payload to Jira:")
    print(payload)

    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.post(
            url,
            headers=_build_jira_auth_header(),
            json=payload,
        )

        if response.status_code >= 400:
            print("Jira API error")
            print(f"Status code : {response.status_code}")
            print(f"Response    : {response.text}")
            return

        issue = response.json()
        issue_key = issue.get("key")
        print(f"Jira issue created: {issue_key}")

# Main monitoring loop

async def monitor_cmms_order() -> None:
    """
    Monitor a CMMS maintenance order and react to workflow transitions.

    The function continuously retrieves the process status and triggers
    Jira issue creation when a Planning → Acceptance transition is detected.
    """
    last_known_status_id: Optional[int] = None
    jira_triggered: bool = False

    async with httpx.AsyncClient(verify=False) as client:
        token = await login_cmms(client)

        while True:
            try:
                current_status_id = await fetch_order_process_status(
                    client,
                    token,
                )

                status_name = resolve_process_status_name(
                    current_status_id
                )

                print(
                    f"CMMS status: {status_name} "
                    f"(id={current_status_id})"
                )

                if (
                    last_known_status_id is not None
                    and has_transitioned_to_acceptance(
                        last_known_status_id,
                        current_status_id,
                    )
                    and not jira_triggered
                ):
                    create_jira_issue()
                    jira_triggered = True

                last_known_status_id = current_status_id

            except Exception as exc:
                print(f"CMMS polling error: {exc}")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(monitor_cmms_order())
