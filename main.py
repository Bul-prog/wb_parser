import pandas as pd
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import QUERY, MAX_PRODUCTS, PRICE, RAITING
from utils import human_sleep, clear_performance_logs
from parser import (
    scroll_page,
    parse_list,
    parse_card,
)


def start_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--lang=ru-RU")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """
    )
    driver.set_page_load_timeout(40)
    return driver

def main():
    driver = start_driver()

    search_url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={quote(QUERY)}"
    driver.get(search_url)

    human_sleep(4.5, 6.0)
    scroll_page(driver)

    products = parse_list(driver)[:MAX_PRODUCTS]
    full_data = []

    for i, product in enumerate(products, start=1):
        print(f"Обрабатываем {i}/{len(products)}")

        try:
            clear_performance_logs(driver)
            driver.get(product["Ссылка"])
            human_sleep(3.0, 4.5)

            row = parse_card(driver, product)
            full_data.append(row)
        except Exception as error:
            print(f"Ошибка при обработке карточки {product['Ссылка']}: {type(error).__name__}: {error}")
            full_data.append(product)

        human_sleep(2.0, 3.5)

    driver.quit()

    df = pd.DataFrame(full_data)



    df["Цена"] = (
        df["Цена"]
        .astype(str)
        .str.replace("₽", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    df["Цена"] = pd.to_numeric(df["Цена"], errors="coerce")

    df["Рейтинг"] = (
        df["Рейтинг"]
        .astype(str)
        .str.replace(",", ".")
    )
    df["Рейтинг"] = pd.to_numeric(df["Рейтинг"], errors="coerce")

    df["Количество отзывов"] = (
        df["Количество отзывов"]
        .astype(str)
        .str.extract(r"(\d+)", expand=False)
    )
    df["Количество отзывов"] = pd.to_numeric(df["Количество отзывов"], errors="coerce")

    df["Страна"] = (
        df["Страна"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["Артикул"] = df["Артикул"].astype(str).str.extract(r"(\d+)", expand=False)
    df["Остатки"] = pd.to_numeric(df["Остатки"], errors="coerce").fillna(0).astype(int)

    output_columns = [
        "Ссылка",
        "Артикул",
        "Название",
        "Цена",
        "Описание",
        "Изображения",
        "Характеристики",
        "Селлер",
        "Ссылка на селлера",
        "Размеры",
        "Остатки",
        "Рейтинг",
        "Количество отзывов",
        "Страна",
    ]

    for col in output_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[output_columns]
    df.to_excel("полный_каталог.xlsx", index=False)

    filtered = df[
        (df["Рейтинг"].notna()) &
        (df["Рейтинг"] >= RAITING) &
        (df["Цена"] <= PRICE) &
        (df["Страна"] == "россия")
    ]

    filtered.to_excel("выборка.xlsx", index=False)

    print("Готово!")


if __name__ == "__main__":
    main()