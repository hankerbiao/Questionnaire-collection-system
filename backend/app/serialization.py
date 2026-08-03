from typing import Any

from bson import ObjectId
from datetime import datetime


def json_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value
