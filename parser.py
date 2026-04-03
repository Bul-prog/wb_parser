import json
import re

from selenium.webdriver.common.by import By

from utils import (
    human_sleep,
    get_performance_messages,
    walk_json,
    extract_product_id_from_link,
)


def scroll_page(driver):
    last_height = 0
    for _ in range(6):
        driver.execute_script("window.scrollBy(0, 1400);")
        human_sleep(1.2, 2.2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def parse_list(driver):
    items = driver.find_elements(By.CLASS_NAME, "product-card")
    data = []

    for item in items:
        try:
            link = item.find_element(By.TAG_NAME, "a").get_attribute("href")
            name = item.find_element(By.CLASS_NAME, "product-card__name").text
            price = item.find_element(By.CLASS_NAME, "price__lower-price").text
            text = item.text

            rating = ""
            match_rating = re.search(r"\d[.,]\d", text)
            if match_rating:
                rating = match_rating.group(0)

            reviews = ""
            match_reviews = re.search(r"(\d+)\s*отзы", text, re.IGNORECASE)
            if match_reviews:
                reviews = match_reviews.group(1)

            product_id = extract_product_id_from_link(link)

            data.append({
                "Ссылка": link,
                "Артикул": product_id,
                "Название": name,
                "Цена": price,
                "Описание": "",
                "Изображения": "",
                "Характеристики": "",
                "Селлер": "",
                "Ссылка на селлера": "",
                "Размеры": "",
                "Остатки": "",
                "Рейтинг": rating,
                "Количество отзывов": reviews,
                "Страна": ""
            })
        except Exception:
            continue

    return data


def find_product_json_in_network(driver, product_id):
    messages = get_performance_messages(driver)
    candidates = []

    for msg in messages:
        try:
            if msg.get("method") != "Network.responseReceived":
                continue

            params = msg.get("params", {})
            response = params.get("response", {})
            url = response.get("url", "")
            mime = response.get("mimeType", "")
            request_id = params.get("requestId")

            if not request_id:
                continue

            url_lower = url.lower()
            mime_lower = mime.lower()

            if (
                    "json" in mime_lower
                    or "card.wb.ru" in url_lower
                    or "basket" in url_lower
                    or "detail" in url_lower
                    or "catalog" in url_lower
            ):
                candidates.append(request_id)
        except Exception:
            continue

    for request_id in candidates:
        try:
            body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            text = body.get("body", "")
            if not text:
                continue

            data = json.loads(text)

            for node in walk_json(data):
                node_id = (
                        node.get("id")
                        or node.get("nm_id")
                        or node.get("nmId")
                        or node.get("imt_id")
                )

                if str(node_id) == str(product_id):
                    if any(
                            key in node
                            for key in ("sizes", "supplier", "supplierId", "options", "feedbacks", "pics", "name")
                    ):
                        return node
        except Exception:
            continue

    return None


def parse_dom_description(driver):
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return ""

    match = re.search(r"Описание\s*\n(.+?)(?:\n[A-ЯЁ][^\n]{0,60}\n|$)", body_text, re.S)
    return match.group(1).strip() if match else ""


def parse_dom_characteristics(driver):
    characteristics = {}

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return characteristics

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]

    start_idx = None
    for i, line in enumerate(lines):
        if line == "Артикул":
            start_idx = i
            break

    if start_idx is None:
        return characteristics

    stop_words = {
        "Дополнительная информация",
        "Описание",
        "Отзывы и вопросы",
        "Смотрите также",
        "Похожие товары",
    }

    section = []
    for line in lines[start_idx:]:
        if line in stop_words:
            break
        section.append(line)

    i = 0
    while i < len(section) - 1:
        key = section[i]
        value = section[i + 1]

        if key and value and key != value:
            characteristics[key] = value
            i += 2
        else:
            i += 1

    return characteristics


def try_open_characteristics(driver):
    xpaths = [
        "//*[contains(text(), 'Характеристики и описание')]",
        "//button[contains(., 'Характеристики и описание')]",
        "//*[contains(text(), 'Характеристики')]",
        "//button[contains(., 'Характеристики')]",
    ]

    for xpath in xpaths:
        try:
            button = driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
            human_sleep(0.7, 1.2)
            driver.execute_script("arguments[0].click();", button)
            human_sleep(1.2, 2.0)
            return True
        except Exception:
            continue

    return False


def build_image_links_from_product(product, product_id):
    images = []

    pics = product.get("pics") or product.get("picsCount") or 0
    try:
        pics = int(pics)
    except Exception:
        pics = 0

    if pics > 0 and product_id.isdigit():
        basket_num = int(product_id) // 100000
        for i in range(1, pics + 1):
            images.append(
                f"https://images.wbstatic.net/c516x688/{basket_num}/{product_id}/images/big/{i}.jpg"
            )

    for key in ("media", "photos", "images"):
        value = product.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.startswith("http"):
                    images.append(item)
                elif isinstance(item, dict):
                    for image_key in ("big", "c516x688", "url", "src"):
                        image_value = item.get(image_key)
                        if isinstance(image_value, str) and image_value.startswith("http"):
                            images.append(image_value)

    unique_images = []
    seen = set()
    for image in images:
        if image not in seen:
            seen.add(image)
            unique_images.append(image)

    return ",".join(unique_images)


def extract_fields_from_product_json(product, base_row):
    row = dict(base_row)
    product_id = str(base_row.get("Артикул", "")).strip()

    description = ""
    for key in ("description", "desc", "seo", "subtitle"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            description = value.strip()
            break
    row["Описание"] = description

    if not row.get("Количество отзывов"):
        for key in ("feedbacks", "feedbackCount", "commentsCnt"):
            value = product.get(key)
            if value not in (None, ""):
                row["Количество отзывов"] = value
                break

    if not row.get("Рейтинг"):
        for key in ("rating", "reviewRating"):
            value = product.get(key)
            if value not in (None, ""):
                row["Рейтинг"] = value
                break

    supplier = ""
    for key in ("supplier", "supplierName", "brand"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            supplier = value.strip()
            break
    row["Селлер"] = supplier

    supplier_id = product.get("supplierId") or product.get("supplier_id") or ""
    row["Ссылка на селлера"] = (
        f"https://seller.wildberries.ru/supplier/{supplier_id}" if supplier_id else ""
    )

    characteristics = {}

    options = product.get("options")
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict):
                name = str(option.get("name", "")).strip()
                value = str(option.get("value", "")).strip()
                if name:
                    characteristics[name] = value

    if not characteristics:
        for key in ("characteristics", "params"):
            items = product.get(key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        name = str(item.get("name", "")).strip()
                        value = str(item.get("value", "")).strip()
                        if name:
                            characteristics[name] = value

    if not characteristics:
        specs = product.get("specs")
        if isinstance(specs, list):
            for item in specs:
                if isinstance(item, dict):
                    name = str(item.get("title", "")).strip()
                    value = str(item.get("value", "")).strip()
                    if name:
                        characteristics[name] = value

    row["Характеристики"] = json.dumps(characteristics, ensure_ascii=False)

    country = ""
    for key in ("country", "madeIn", "countryName"):
        value = product.get(key)
        if isinstance(value, str) and value.strip():
            country = value.strip()
            break

    if not country:
        for key, value in characteristics.items():
            if "страна" in key.lower():
                country = str(value).strip()
                break

    row["Страна"] = country

    sizes_list = []
    total_stocks = 0

    sizes = product.get("sizes")
    if isinstance(sizes, list):
        for size in sizes:
            if not isinstance(size, dict):
                continue

            size_name = str(size.get("name", "")).strip()
            if size_name and size_name not in sizes_list:
                sizes_list.append(size_name)

            stocks = size.get("stocks")
            if isinstance(stocks, list):
                for stock in stocks:
                    if isinstance(stock, dict):
                        qty = stock.get("qty", 0)
                        try:
                            total_stocks += int(qty)
                        except Exception:
                            pass

    row["Размеры"] = ",".join(sizes_list)
    row["Остатки"] = total_stocks
    row["Изображения"] = build_image_links_from_product(product, product_id)

    return row


def parse_card(driver, base_row):
    result = dict(base_row)
    product_id = str(base_row.get("Артикул", "")).strip()

    try_open_characteristics(driver)
    human_sleep(1.0, 1.8)

    product_json = find_product_json_in_network(driver, product_id)
    if product_json:
        result = extract_fields_from_product_json(product_json, result)

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        body_text = ""

    if not result.get("Описание"):
        match = re.search(r"Описание\s*\n(.+?)(?:\n[A-ЯЁ][^\n]{0,60}\n|$)", body_text, re.S)
        if match:
            result["Описание"] = match.group(1).strip()

    if not result.get("Характеристики") or result.get("Характеристики") == "{}":
        dom_characteristics = parse_dom_characteristics(driver)
        if dom_characteristics:
            result["Характеристики"] = json.dumps(dom_characteristics, ensure_ascii=False)

            if not result.get("Страна"):
                for key, value in dom_characteristics.items():
                    if "страна" in key.lower():
                        result["Страна"] = str(value).strip()
                        break

    if not result.get("Страна"):
        match = re.search(r"Страна производства\s*\n?([А-Яа-яA-Za-z\- ]+)", body_text, re.I)
        if match:
            result["Страна"] = match.group(1).strip()

    return result
