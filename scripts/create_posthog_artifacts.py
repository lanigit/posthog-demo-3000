import requests
import sys
from argparse import ArgumentParser
import os
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import quote

REQUIRED_SCOPES = [
    "action:write",
    "cohort:write",
    "dashboard:write",
    "experiment:write",
    "feature_flag:write",
    "insight:write",
    "query:read",
    "survey:write",
]


def precheck_scopes(api_key):
    """Verify the Personal API key has all required scopes before doing any work.

    Strategy:
    1. Hit GET /api/users/@me/ and look for an explicit scopes list on the user
       or the key. PostHog versions vary in where this surfaces (top-level,
       under `team`, under `organization`, or as a `scoped_*` field), so we
       search broadly.
    2. If no scopes can be discovered that way, fall back to a cheap probe:
       POST /api/projects/<project_id>/cohorts/ with an empty body. A 403 on
       a scope check returns a `detail` like "API key missing required scope
       'cohort:write'.". We parse that and surface the missing scopes.

    On any missing scopes, print a clear, actionable error and exit 1.
    """
    auth_headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base_host = host.replace(".i.posthog.com", ".posthog.com")
    discovered_scopes = None

    # Step 1: try /api/users/@me/
    try:
        me_resp = requests.get(f"{base_host}/api/users/@me/", headers=auth_headers, timeout=15)
        if me_resp.status_code == 401:
            print("ERROR: Personal API key is invalid or expired (HTTP 401 on /api/users/@me/).")
            print("Update at: https://us.posthog.com/settings/user-api-keys")
            sys.exit(1)
        if me_resp.status_code == 200:
            payload = me_resp.json() if me_resp.content else {}
            # Search common locations for a scopes list.
            candidates = []
            if isinstance(payload, dict):
                for key in ("scopes", "scoped_scopes", "key_scopes"):
                    val = payload.get(key)
                    if isinstance(val, list):
                        candidates.extend(val)
                # Some versions nest the key info under `personal_api_key` or similar.
                for nest_key in ("personal_api_key", "api_key", "current_key"):
                    nested = payload.get(nest_key)
                    if isinstance(nested, dict):
                        nv = nested.get("scopes")
                        if isinstance(nv, list):
                            candidates.extend(nv)
            if candidates:
                discovered_scopes = set(candidates)
    except requests.RequestException as e:
        print(f"ERROR: could not reach PostHog at {base_host} during scope precheck: {e}")
        sys.exit(1)

    missing = []

    if discovered_scopes is not None:
        # Wildcard "*" grants everything in PostHog scope conventions.
        if "*" in discovered_scopes:
            missing = []
        else:
            missing = [s for s in REQUIRED_SCOPES if s not in discovered_scopes]
    else:
        # Step 2: fall back to a cheap probe. POST an empty cohort body and
        # parse the 403 detail message for missing-scope hints.
        probe_url = f"{base_host}/api/projects/{project_id}/cohorts/"
        try:
            probe = requests.post(probe_url, headers=auth_headers, json={}, timeout=15)
        except requests.RequestException as e:
            print(f"ERROR: could not reach PostHog at {base_host} during scope precheck: {e}")
            sys.exit(1)

        if probe.status_code == 403:
            try:
                detail = probe.json().get("detail", "") or ""
            except ValueError:
                detail = probe.text or ""
            # Probe only tests cohort:write. If THAT scope is missing, surface it.
            # Otherwise we cannot infer the rest from one probe — assume key is
            # too narrow and warn the user to grant all required scopes.
            if "cohort:write" in detail or "scope" in detail.lower():
                # Could be exactly cohort:write, or could be a generic "missing scope" reply.
                # Be conservative: report all required scopes as unverifiable.
                if "cohort:write" in detail:
                    missing = ["cohort:write"]
                else:
                    missing = list(REQUIRED_SCOPES)
            else:
                # 403 for a non-scope reason (e.g., project access). Treat as fatal.
                print("ERROR: Personal API key is forbidden from accessing this project (HTTP 403).")
                print(f"  detail: {detail}")
                print("Update at: https://us.posthog.com/settings/user-api-keys")
                sys.exit(1)
        elif probe.status_code in (400, 422):
            # Empty body rejected on validation grounds — auth + scope are fine for cohort:write.
            # We still cannot verify the other scopes; warn the user we could not enumerate.
            print(
                "WARNING: could not enumerate Personal API key scopes via /api/users/@me/; "
                "cohort:write probe succeeded but other scopes are unverified. "
                "If a later request 403s, re-check scopes at "
                "https://us.posthog.com/settings/user-api-keys"
            )
            missing = []
        elif probe.status_code in (200, 201):
            # Unexpectedly created something — try to clean up but don't block on it.
            missing = []
            try:
                created = probe.json()
                cid = created.get("id") if isinstance(created, dict) else None
                if cid:
                    requests.delete(f"{probe_url}{cid}/", headers=auth_headers, timeout=15)
            except Exception:
                pass
        else:
            print(
                f"ERROR: unexpected response during scope precheck (HTTP {probe.status_code}). "
                f"Body: {probe.text[:300]}"
            )
            sys.exit(1)

    if missing:
        print("ERROR: Personal API key is missing required scope(s):")
        for s in missing:
            print(f"  - {s}")
        print("Update at: https://us.posthog.com/settings/user-api-keys")
        sys.exit(1)


parser = ArgumentParser()
parser.add_argument("-k", "--personal_api_key",
                    help="PostHog Personal API Key", required=False)
parser.add_argument("-p", "--posthog_api_base_url",
                    help="PostHog API Host", required=False)
parser.add_argument("--project_id", help="PostHog Project Id", required=False)
args = parser.parse_args()

# Load env from project root
project_root_env = Path(__file__).resolve().parents[1] / '.env'
if project_root_env.exists():
    load_dotenv(dotenv_path=project_root_env)

personal_api_key = args.personal_api_key or os.getenv('PH_PERSONAL_API_KEY')
project_id = args.project_id or os.getenv('PH_PROJECT_ID')
host = os.getenv('PH_HOST')
if not personal_api_key:
    raise SystemExit('PH_PERSONAL_API_KEY must be set in env or passed via -k')
if not project_id:
    raise SystemExit('PH_PROJECT_ID must be set in env or passed via --project_id')
if not host:
    raise SystemExit('PH_HOST must be set in env')

# The URL to which you want to send the POST request
url = args.posthog_api_base_url or f"{host.replace('.i.posthog.com','.posthog.com')}/api/projects/{project_id}"

# The Bearer token for authentication
token = personal_api_key

# Headers including the Bearer token for authorization
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# The JSON payload to be sent in the POST request
actions_ids = {}
actions_endpoint = '/actions/'
actions_data = [
        {
            "name": "Subscription Cancelled",
            "tags": ['demo'],
            "steps": [
                {
                    "event": "plan_changed",
                    "properties": [
                        {
                            "key": "new_plan",
                            "type": "event",
                            "value": [
                                "Free"
                            ],
                            "operator": "exact"
                        }
                    ]
                }
            ]
        },
        {
            "name": "Paid Plan Purchase",
            "tags": ['demo'],
            "steps": [
                {
                    "event": "plan_changed",
                    "properties": [
                        {
                            "key": "new_plan",
                            "type": "event",
                            "value": [
                                "Premium",
                                "Max-imal"
                            ],
                            "operator": "exact"
                        }
                    ]
                }
            ]
        },
        {
            "name": "Watched a movie",
            "tags": ['demo'],
            "description": "Watched a movie",
            "steps": [
                {
                    "event": "$pageview",
                    "url": "movie/",
                    "url_matching": "contains"
                }
            ]
        },
        {
            "name": "Select Free Plan",
            "tags": ['demo'],
            "steps": [
                {
                    "event": "$autocapture",
                    "properties": None,
                    "selector": ".container .col-md-4:nth-child(1) > .text-decoration-none"
                }
            ]
        },
        {
            "name": "Select Premium Plan",
            "tags": ['demo'],
            "steps": [
                {
                    "event": "$autocapture",
                    "properties": None,
                    "selector": ".container .col-md-4:nth-child(2) > .text-decoration-none"
                }
            ]
        },
        {
            "name": "Select Maxi-Mal Plan",
            "tags": ['demo'],
            "steps": [
                {
                    "event": "$autocapture",
                    "properties": None,
                    "selector": ".container .col-md-4:nth-child(3) > .text-decoration-none"
                }
            ]
        }
    ]

cohorts_ids = {}
cohorts_endpoint = '/cohorts/'
cohorts_data = [
        {
            "name": "Adult Subscribers",
            "description": "All Subscribers who are adults and thus can watch action movies",
            "filters": {
                "properties": {
                    "type": "OR",
                    "values": [
                        {
                            "type": "OR",
                            "values": [
                                {
                                    "key": "is_adult",
                                    "type": "person",
                                    "value": [
                                        "Yes"
                                    ],
                                    "negation": False,
                                    "operator": "exact"
                                }
                            ]
                        }
                    ]
                }
            }
        },
        {
            "name": "Max-imal users who watched a movie in the last 30 days",
            "description": "",
            "filters": {
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "type": "AND",
                            "values": [
                                {
                                    "type": "behavioral",
                                    "value": "performed_event",
                                    "negation": False,
                                    "event_type": "actions",
                                    "explicit_datetime": "-30d"
                                },
                                {
                                    "key": "plan",
                                    "type": "person",
                                    "value": [
                                        "Max-imal"
                                    ],
                                    "negation": False,
                                    "operator": "exact"
                                }
                            ]
                        }
                    ]
                }
            }
        },
        {
            "name": "People who watched 5 movies recently",
            "filters": {
                "properties": {
                    "type": "OR",
                    "values": [
                        {
                            "type": "OR",
                            "values": [
                                {
                                    "type": "behavioral",
                                    "value": "performed_event_multiple",
                                    "negation": False,
                                    "operator": "gte",
                                    "event_type": "actions",
                                    "operator_value": 5,
                                    "explicit_datetime": "-30d"
                                }
                            ]
                        }
                    ]
                }
            }
        }
    ]

insights_endpoint = '/insights/'

movie_views_trend_data = {
    "name":"Movie Views by Plan Type",
     "query": {
  "kind": "InsightVizNode",
  "source": {
    "kind": "TrendsQuery",
    "properties": {
      "type": "AND",
      "values": [
        {
          "type": "AND",
          "values": [
            {
              "key": "plan",
              "type": "person",
              "value": "is_set",
              "operator": "is_set"
            }
          ]
        }
      ]
    },
    "dateRange": {
      "date_to": None,
      "date_from": "-30d"
    },
    "series": [
      {
        "kind": "ActionsNode",
        "math": "total"
      }
    ],
    "interval": "week",
    "breakdownFilter": {
      "breakdowns": [
        {
          "type": "person",
          "property": "plan"
        }
      ]
    },
    "trendsFilter": {
      "display": "ActionsLineGraph"
    }
  },
  "full": True
},
 "saved": True,
 "tags": ["demo"]
}

purchase_funnel_data = {
    "name": "Paid plan purchase funnel",
    "query": {
  "kind": "InsightVizNode",
  "source": {
    "kind": "FunnelsQuery",
    "dateRange": {
      "date_from": "-30d"
    },
    "series": [
      {
        "kind": "EventsNode",
        "event": "$pageview",
        "name": "$pageview",
        "custom_name": "Home Page",
        "properties": [
          {
            "key": "$pathname",
            "type": "event",
            "value": [
              "/"
            ],
            "operator": "exact"
          }
        ]
      },
      {
        "kind": "EventsNode",
        "event": "$pageview",
        "name": "$pageview",
        "custom_name": "Plans Page",
        "properties": [
          {
            "key": "$pathname",
            "type": "event",
            "value": [
              "/plans"
            ],
            "operator": "exact"
          }
        ]
      },
      {
        "kind": "EventsNode",
        "event": "$pageview",
        "name": "$pageview",
        "custom_name": "Signup Page",
        "properties": [
          {
            "key": "$pathname",
            "type": "event",
            "value": [
              "/signup"
            ],
            "operator": "exact"
          }
        ]
      },
      {
        "kind": "ActionsNode",
        "name": "Paid Plan Purchase"
      }
    ],
    "funnelsFilter": {
      "funnelVizType": "steps"
    }
  },
  "full": True
},
"saved": True,
 "tags": ["demo"]
}

movie_retention_data = {
    "name": "Weekly Movie Watch Retention",
    "query":{
  "kind": "InsightVizNode",
  "source": {
    "kind": "RetentionQuery",
    "retentionFilter": {
      "retentionType": "retention_first_time",
      "totalIntervals": 5,
      "returningEntity": {
        "id": 42493,
        "name": "Watched a movie (Test)",
        "type": "actions",
        "order": 0,
        "uuid": "fafa227f-4eed-4dd6-b007-63f748129444"
      },
      "targetEntity": {
        "id": 42493,
        "name": "Watched a movie (Test)",
        "type": "actions",
        "order": 0,
        "uuid": "7a9325b9-85df-44d7-a06e-b62cec8e7bb9"
      },
      "period": "Week"
    }
  },
  "full": True
},
"saved": True,
 "tags": ["demo"]
}

path_data = {
    "name": "Where do people go after visiting the homepage",
    "query": {
  "kind": "InsightVizNode",
  "source": {
    "kind": "PathsQuery",
    "pathsFilter": {
      "includeEventTypes": [
        "$pageview"
      ],
      "pathGroupings": [
        "/movie/*"
      ]
    }
  },
  "full": True
},
"saved": True,
 "tags": ["demo"]
}

feature_flag_endpoint = '/feature_flags/'
feature_flag_data = {
            "name": "Turns Hogflix from family friendly to action movies.",
            "key": "action_mode_on",
            "tags": ["demo"],
            "filters": {
                "groups": [
                    {
                        "variant": None,
                        "properties": [
                            {
                                "key": "id",
                                "type": "cohort",
                            }
                        ],
                        "rollout_percentage": 100
                    }
                ],
                "payloads": {},
                "multivariate": None
            }
        }

class PostHogForbiddenError(Exception):
    """Raised when PostHog returns 403 on an artifact-creation call.

    Carries the endpoint and response body so the caller can hint at the
    likely missing scope.
    """

    def __init__(self, endpoint, status_code, body):
        self.endpoint = endpoint
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code} on {endpoint}: {body[:300]}")


def make_posthog_api_request(endpoint, data):
    response = requests.post(url + endpoint, headers=headers, json=data)
    if response.status_code == 201:
        return response.json()
    if response.status_code == 403:
        raise PostHogForbiddenError(endpoint, response.status_code, response.text or "")
    print(f"Request failed with status code {response.status_code}")
    print("Response:", response.text)
    try:
        return response.json()
    except Exception:
        return None


# Map of endpoint -> the scope most likely required to write to it.
ENDPOINT_SCOPE_HINTS = {
    '/actions/': 'action:write',
    '/cohorts/': 'cohort:write',
    '/insights/': 'insight:write',
    '/feature_flags/': 'feature_flag:write',
    '/dashboards/': 'dashboard:write',
    '/experiments/': 'experiment:write',
    '/surveys/': 'survey:write',
}


def report_403_and_reraise(err, action_label):
    """Print a clear scope hint for a 403 and re-raise the original exception."""
    hint = ENDPOINT_SCOPE_HINTS.get(err.endpoint, 'unknown')
    print(f"ERROR: HTTP 403 while {action_label} (endpoint {err.endpoint}).")
    print(f"  scope '{hint}' is likely missing from the Personal API key.")
    print("  Update at: https://us.posthog.com/settings/user-api-keys")
    raise err


def get_existing_by(endpoint, match_key, match_value):
    try:
        resp = requests.get(url + endpoint + f"?search={quote(str(match_value))}", headers=headers)
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data.get('results', data if isinstance(data, list) else [])
        for item in items:
            if item.get(match_key) == match_value:
                return item
    except Exception:
        return None
    return None

# Verify the Personal API key has all required scopes BEFORE any artifact work.
precheck_scopes(personal_api_key)

# Making the POST request

# --- actions ---
try:
    for data in actions_data:
        # Try to find existing action by name
        existing = get_existing_by(actions_endpoint, 'name', data['name'])
        if existing:
            actions_ids[data['name']] = existing['id']
            continue
        response = make_posthog_api_request(actions_endpoint, data)
        if response and 'id' in response:
            actions_ids[data['name']] = response['id']
except PostHogForbiddenError as e:
    report_403_and_reraise(e, "creating actions")

cohorts_data[1]['filters']['properties']['values'][0]['values'][0]['key'] =  actions_ids.get('Watched a movie')
cohorts_data[2]['filters']['properties']['values'][0]['values'][0]['key'] =  actions_ids.get('Watched a movie')

# --- cohorts ---
try:
    for data in cohorts_data:
        existing = get_existing_by(cohorts_endpoint, 'name', data['name'])
        if existing:
            cohorts_ids[data['name']] = existing['id']
            continue
        response = make_posthog_api_request(cohorts_endpoint, data)
        if response and 'id' in response:
            cohorts_ids[data['name']] = response['id']
except PostHogForbiddenError as e:
    report_403_and_reraise(e, "creating cohorts")

# --- insights ---
try:
    movie_views_trend_data['query']['source']['series'][0]['id'] = actions_ids.get('Watched a movie')
    existing_mv = get_existing_by(insights_endpoint, 'name', movie_views_trend_data['name'])
    if not existing_mv:
        response = make_posthog_api_request(insights_endpoint, movie_views_trend_data)

    purchase_funnel_data['query']['source']['series'][3]['id'] = actions_ids.get('Paid Plan Purchase')
    existing_pf = get_existing_by(insights_endpoint, 'name', purchase_funnel_data['name'])
    if not existing_pf:
        response = make_posthog_api_request(insights_endpoint, purchase_funnel_data)

    movie_retention_data['query']['source']['retentionFilter']['targetEntity']['id'] = actions_ids.get('Watched a movie')
    movie_retention_data['query']['source']['retentionFilter']['returningEntity']['id'] = actions_ids.get('Watched a movie')

    existing_ret = get_existing_by(insights_endpoint, 'name', movie_retention_data['name'])
    if not existing_ret:
        response = make_posthog_api_request(insights_endpoint, movie_retention_data)

    existing_path = get_existing_by(insights_endpoint, 'name', path_data['name'])
    if not existing_path:
        response = make_posthog_api_request(insights_endpoint, path_data)
except PostHogForbiddenError as e:
    report_403_and_reraise(e, "creating insights")

# --- feature flag ---
try:
    feature_flag_data['filters']['groups'][0]['properties'][0]['value'] = cohorts_ids.get('Adult Subscribers')
    existing_ff = get_existing_by(feature_flag_endpoint, 'key', feature_flag_data['key'])
    if not existing_ff:
        response = make_posthog_api_request(feature_flag_endpoint, feature_flag_data)
except PostHogForbiddenError as e:
    report_403_and_reraise(e, "creating feature flag")


