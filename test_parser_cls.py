import time
from database import Database
from parser_cls import AvitoParse
from dto import AvitoConfig

def test_parser():
    db = Database()
    
    # Мокаем базовый конфиг
    config = AvitoConfig(
        urls=["https://www.avito.ru/moskva/telefony/apple-ASgBAgICAUTkAwQ"],
        keys_word_white_list=[],
        keys_word_black_list=[],
        seller_black_list=[],
        min_price=1000,
        max_price=1000000,
        max_age=3600*24,
        geo="",
        ignore_reserv=True,
        ignore_promotion=False,
        pause_between_links=2,
        parse_views=False,
        one_time_start=True
    )
    
    # Отключаем отправку в ТГ для теста (если нужно - можно включить)
    config.tg_token = ""
    config.tg_chat_id = ""
    
    parser = AvitoParse(config=config)
    parser.parse()
    
    print(f"Тест завершен. Успешных запросов: {parser.good_request_count}, Плохих: {parser.bad_request_count}")

if __name__ == "__main__":
    test_parser()