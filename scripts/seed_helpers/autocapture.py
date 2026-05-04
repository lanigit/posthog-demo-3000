"""Synthesize $autocapture, $rageclick, and $dead_click events."""


def synthesize_autocapture(distinct_id, page, timestamp, session_props):
    raise NotImplementedError


def synthesize_rageclick(distinct_id, page, timestamp, session_props):
    raise NotImplementedError


def synthesize_dead_click(distinct_id, page, timestamp, session_props):
    raise NotImplementedError
