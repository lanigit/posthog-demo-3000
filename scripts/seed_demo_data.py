from posthog import Posthog
from datetime import datetime,timedelta
from faker import Faker
from argparse import ArgumentParser
import random
import csv
import sys
from argparse import ArgumentParser
from pathlib import Path
import os
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.seed_helpers.browser_context import make_session_properties
from scripts.seed_helpers.growth import (
    daily_user_count,
    behavioral_profile,
    events_per_session,
    is_user_active_on_day,
)

# The PostHog Python SDK injects host-machine $os/$os_version into every event,
# overriding caller-supplied values. Strip those keys from the SDK's system
# context so the per-session device profile wins. ($python_runtime/$python_version
# stay; they're harmless metadata.)
import posthog.client as _ph_client
_original_system_context = _ph_client.system_context
def _system_context_without_os():
    ctx = dict(_original_system_context())
    ctx.pop("$os", None)
    ctx.pop("$os_version", None)
    return ctx
_ph_client.system_context = _system_context_without_os


def _hash_seed(value):
    """Stable positive 31-bit int seed from any value."""
    return abs(hash(str(value))) & 0x7FFFFFFF

days_to_generate = 30
number_of_iterations = 100

parser = ArgumentParser()
parser.add_argument("-d", "--number_of_days",
                    help="Number of days before today to generate data from",default=30, required=False)
parser.add_argument("-i", "--number_of_iterations",
                    help="Number of iterations of the data generator",default=100, required=False)
parser.add_argument("-k", "--posthog_api_key",
                    help="PostHog Project API Key", required=False)
parser.add_argument("-p", "--posthog_host",
                    help="PostHog Host", required=False)
args = parser.parse_args()

# Load .env from project root to support Codespaces/devcontainer auto-creation
project_root_env = Path(__file__).resolve().parents[1] / '.env'
if project_root_env.exists():
  load_dotenv(dotenv_path=project_root_env)

# Fallback to environment variables if CLI params not provided
if not args.posthog_api_key:
  args.posthog_api_key = os.getenv("PH_PROJECT_KEY")
if not args.posthog_host:
  args.posthog_host = os.getenv("PH_HOST")
if not args.posthog_api_key or not args.posthog_host:
  raise SystemExit("PH_PROJECT_KEY and PH_HOST must be provided via flags or environment variables.")

# PostHog Python Client
posthog = Posthog(args.posthog_api_key, 
  host=args.posthog_host,
  debug=True,
  historical_migration=True,
  disable_geoip=False
)

fake = Faker() 

csv_path = Path(__file__).resolve().parent / '500_names_and_emails.csv'
with open(csv_path, newline='') as csvfile:
    csvreader = csv.DictReader(csvfile, delimiter=',')
    fake_users = [row for row in csvreader]

device_properties = [
    {
       "$os": "Mac OS X",
      "$browser": "Chrome",
      "$device_type": "Desktop"
    },
    {
       "$os": "Mac OS X",
      "$browser": "Firefox",
      "$device_type": "Desktop"
    },
    {
       "$os": "Mac OS X",
      "$browser": "Safari",
      "$device_type": "Desktop"
    },{
       "$os": "Windows",
      "$browser": "Chrome",
      "$device_type": "Desktop"
    },
    {
       "$os": "Windows",
      "$browser": "Edge",
      "$device_type": "Desktop"
    },
    {
       "$os": "Windows",
      "$browser": "Firefox",
      "$device_type": "Desktop"
    },
    {
       "$os": "iOS",
      "$browser": "Mobile Safari",
      "$device_type": "Mobile"
    },
    {
       "$os": "Android",
      "$browser": "Android Mobile",
      "$device_type": "Mobile"
    }]

plans = ['Free', 'Premium', 'Max-imal']

# Simple catalog mirror of pop_db.py entries for titles
movies_catalog = {
  1: {"title": "Code & Quills"},
  2: {"title": "Palette of Prickles"},
  3: {"title": "Data Spikes"},
  4: {"title": "Fists of Fury"},
  5: {"title": "Spikes & Consequences"},
  6: {"title": "The Hedge Abides"}
}

def get_random_time(day_offset=None):
    """Random timestamp. If day_offset is set, return a time within that day
    (days_ago=day_offset). Otherwise scatter across the whole window."""
    if day_offset is not None:
        return datetime.now() - timedelta(days=day_offset, seconds=random.randint(0, 86400))
    random_seconds = random.randint(0, int(args.number_of_days) * 86400)
    return datetime.now() - timedelta(seconds=random_seconds)


def _user_id_int(email):
    """Stable positive int per email for behavioral_profile()."""
    return abs(hash(email)) & 0x7FFFFFFF

def capture_pageview(url, timestamp, client_properties, distinct_id, groups = {}):
   properties = {
      "$current_url": url,
      "$host": 'hogflix.net',
      "$pathname": url.replace('https://hogflix.net', ''),
      **client_properties
   }
   capture_event('$pageview',properties,timestamp, distinct_id, groups)
   
   
# Convert and capture Amplitude data
def capture_event(event, extra_properties, timestamp, distinct_id, groups = {}):

  payload = {
    "event": event,
    "distinct_id": distinct_id,
    "properties": {
      "timestamp": timestamp,
      **extra_properties
    },
    "timestamp": timestamp,
    "groups": groups
  }

  posthog.capture(
    event=payload["event"],
    distinct_id=payload["distinct_id"],
    properties=payload["properties"],
    timestamp=payload["timestamp"],
    groups=payload["groups"]
  )

def get_client_properties(user = None):
   session_id = fake.uuid4()
   session_props = make_session_properties(_hash_seed(session_id))
   if (user is not None):
      properties= {
         **session_props,
         "$ip": user['ip'],
         "$session_id": session_id,
         "$active_feature_flags": ["action_mode_on"],
         "$feature/action_mode_on": True if user['is_adult'] == 'Yes' else False,
         "$set": {
            "email": user['email'],
            "is_adult": user['is_adult'],
            "plan": user['plan']
         }
      }
   else:
      properties= {
         **session_props,
         "$ip": fake.ipv4_public(),
         "$session_id": session_id,
         "$active_feature_flags": ["action_mode_on"],
         "$feature/action_mode_on": random.choice([True,False])
      }
   return properties

def browse_and_watch_movie(number = 1, user=None, day_offset=None):
   fake_user = user or random.choice(fake_users)
   distinct_id = fake_user['email']

   posthog.group_identify('family', fake_user['family_id'], {
      'name': fake_user['last_name']
   })

   groups = {'family': fake_user['family_id']}

   for i in range(random.randint(1, number)):
        timestamp = get_random_time(day_offset=day_offset)
        client_properties = get_client_properties(user=fake_user)
        
        capture_event(event='user_logged_in', extra_properties=client_properties, timestamp=timestamp, distinct_id=distinct_id, groups=groups)

        timestamp = timestamp + timedelta(minutes=random.randint(1,5))

        capture_pageview(url='https://hogflix.net/', client_properties = client_properties,timestamp=timestamp, distinct_id = distinct_id, groups=groups)

        movie_id = random.randint(1,3)

        timestamp = timestamp + timedelta(minutes=random.randint(1,15))

        capture_pageview(url=f'https://hogflix.net/movie/{movie_id}', client_properties = client_properties, timestamp=timestamp, distinct_id = distinct_id, groups=groups)

        # Simulate occasional revenue events
        if random.randrange(100) < 25:
            action_type = random.choice(['buy','rent'])
            price = 14.99 if action_type == 'buy' else 4.99
            value_minor = int(round(price * 100))
            movie_title = movies_catalog.get(movie_id, {}).get('title', f'Movie {movie_id}')

            # Intent event (no revenue aggregation)
            capture_event(
               event=f'movie_{action_type}_intent',
               extra_properties={
                  **client_properties,
                  "movie_id": movie_id,
                  "movie_title": movie_title,
                  "action": action_type,
                  "price": price,
                  "currency": "USD",
               },
               timestamp=timestamp + timedelta(minutes=1),
               distinct_id=distinct_id,
               groups=groups,
            )

            # Complete event with value and currency for Revenue Analytics
            capture_event(
               event=f'movie_{action_type}_complete',
               extra_properties={
                  **client_properties,
                  "movie_id": movie_id,
                  "movie_title": movie_title,
                  "action": action_type,
                  "value": value_minor,
                  "currency": "USD",
               },
               timestamp=timestamp + timedelta(minutes=2),
               distinct_id=distinct_id,
               groups=groups,
            )

def anon_browse_homepage_and_plans(day_offset=None):
   client_properties = get_client_properties()
   distinct_id = fake.uuid4()

   timestamp = get_random_time(day_offset=day_offset)

   capture_pageview(url='https://hogflix.net/', client_properties = client_properties,timestamp=timestamp, distinct_id = distinct_id)
   
   timestamp = timestamp + timedelta(minutes=random.randint(1,10))
   
   capture_pageview(url=f'https://hogflix.net/plans', client_properties = client_properties, timestamp=timestamp, distinct_id = distinct_id)

   if random.randrange(100) < 40:
      return None

   timestamp = timestamp + timedelta(minutes=random.randint(1,10))
   
   capture_pageview(url=f'https://hogflix.net/signup', client_properties = client_properties, timestamp=timestamp, distinct_id = distinct_id)

def browse_plans_and_signup(user=None, day_offset=None):
   fake_user = user or random.choice(fake_users)
   client_properties = get_client_properties(user=fake_user)
   distinct_id = fake_user['email']
   timestamp = get_random_time(day_offset=day_offset)

   posthog.group_identify('family', fake_user['family_id'], {
      'name': fake_user['last_name']
   })
    
   groups = {'family': fake_user['family_id']}

   capture_pageview(url='https://hogflix.net/', client_properties = client_properties,timestamp=timestamp, distinct_id = distinct_id, groups=groups)
   
   timestamp = timestamp + timedelta(minutes=random.randint(1,10))
   
   capture_pageview(url=f'https://hogflix.net/plans', client_properties = client_properties, timestamp=timestamp, distinct_id = distinct_id, groups=groups)

   timestamp = timestamp + timedelta(minutes=random.randint(1,10))
   
   capture_pageview(url=f'https://hogflix.net/signup', client_properties = client_properties, timestamp=timestamp, distinct_id = distinct_id, groups=groups)
   
   timestamp = timestamp + timedelta(minutes=random.randint(1,10))
   
   selected_plans = random.sample(plans,2)
   previous_plan = selected_plans[0]
   new_plan = selected_plans[1]
   client_properties = { **client_properties,
                        "previous_plan": previous_plan,
                        "new_plan": new_plan,
                        "$set": {
                           "plan": new_plan
                        }}
   capture_event(event='plan_changed', extra_properties=client_properties, timestamp=timestamp, distinct_id=distinct_id, groups=groups)

   # Emit subscription intent and purchase for Revenue Analytics
   months = 1
   price_dollars = 19.99 if new_plan == 'Max-imal' else 9.99 if new_plan == 'Premium' else 0
   timestamp = timestamp + timedelta(minutes=1)
   capture_event(event='subscription_intent', extra_properties={
      **client_properties,
      'plan': new_plan,
      'months': months,
      'price': int(round(price_dollars * 100)),
      'currency': 'USD',
   }, timestamp=timestamp, distinct_id=distinct_id, groups=groups)

   timestamp = timestamp + timedelta(minutes=1)
   capture_event(event='subscription_purchased', extra_properties={
      **client_properties,
      'plan': new_plan,
      'months': months,
      'price': int(round(price_dollars * 100)),
      'currency': 'USD',
   }, timestamp=timestamp, distinct_id=distinct_id, groups=groups)

total_days = int(args.number_of_days)

# Pre-assign a deterministic signup_days_ago per fake_user. Distribute across
# the window so the growth curve has natural fuel: only old signups can be
# active on early days; recent signups appear later.
user_signups = {
    u['email']: random.Random(u['email']).randint(0, max(1, total_days - 1))
    for u in fake_users
}

# Track which users have already had a signup flow emitted (browse_plans_and_signup)
signed_up_users = set()

print(f"Generating events for {total_days} days, {len(fake_users)} potential users.")

for days_ago in range(total_days, -1, -1):
    target = daily_user_count(days_ago, total_days)
    eligible = [
        u for u in fake_users
        if is_user_active_on_day(_user_id_int(u['email']), days_ago, user_signups[u['email']])
    ]
    if len(eligible) > target:
        eligible = random.Random(days_ago).sample(eligible, target)

    for user in eligible:
        profile = behavioral_profile(_user_id_int(user['email']))

        # First active day for this user => emit the signup flow once.
        if user['email'] not in signed_up_users and user_signups[user['email']] == days_ago:
            browse_plans_and_signup(user=user, day_offset=days_ago)
            signed_up_users.add(user['email'])
            continue

        # Otherwise pick a flow shape based on profile.
        if profile == 'power':
            browse_and_watch_movie(number=4, user=user, day_offset=days_ago)
        elif profile == 'casual':
            browse_and_watch_movie(number=2, user=user, day_offset=days_ago)
        elif profile == 'churned':
            browse_and_watch_movie(number=1, user=user, day_offset=days_ago)
        elif profile == 'bouncer':
            # Bouncers also browse anonymously sometimes
            if random.random() < 0.5:
                anon_browse_homepage_and_plans(day_offset=days_ago)
            else:
                browse_and_watch_movie(number=1, user=user, day_offset=days_ago)

    # A handful of pure-anonymous browse sessions per day (top-of-funnel noise).
    for _ in range(max(1, target // 10)):
        anon_browse_homepage_and_plans(day_offset=days_ago)

    posthog.flush()