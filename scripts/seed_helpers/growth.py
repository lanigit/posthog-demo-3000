"""Growth curve and behavioral cohort distribution."""


def daily_user_count(days_ago: int) -> int:
    """Returns the number of active users for a day N days in the past."""
    raise NotImplementedError  # populated in Phase 3


def behavioral_profile(user_id: int) -> str:
    """Returns 'power' | 'casual' | 'churned' | 'bouncer' deterministically per user_id."""
    raise NotImplementedError  # populated in Phase 3
