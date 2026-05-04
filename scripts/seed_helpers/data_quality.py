"""Intentional data quality variants: typos, JSON-stringified values, format drift."""


def apply_event_typo(event_name):
    raise NotImplementedError


def apply_property_typo(props):
    raise NotImplementedError


def jsonify_property(props, key):
    raise NotImplementedError


def date_format_drift(date_value):
    raise NotImplementedError


def plan_name_drift(plan_name):
    raise NotImplementedError
