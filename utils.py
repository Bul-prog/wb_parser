import json
import random
import re
import time

from config import SLEEP_MIN, SLEEP_MAX


def human_sleep(a=SLEEP_MIN, b=SLEEP_MAX):
    time.sleep(random.uniform(a, b))


def clear_performance_logs(driver):
    try:
        driver.get_log("performance")
    except Exception:
        pass


def get_performance_messages(driver):
    messages = []
    try:
        for entry in driver.get_log("performance"):
            try:
                messages.append(json.loads(entry["message"])["message"])
            except Exception:
                continue
    except Exception:
        pass
    return messages


def walk_json(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_json(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)


def extract_product_id_from_link(link):
    match = re.search(r"/catalog/(\d+)/", link)
    return match.group(1) if match else ""
