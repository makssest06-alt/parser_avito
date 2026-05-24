import logging
from datetime import datetime, timedelta
import re
from models import Item
from dto import AvitoConfig

logger = logging.getLogger(__name__)

class AdsFilter:
    @staticmethod
    def filter_ads(ads: list[Item], config: AvitoConfig) -> list[Item]:
        filtered = ads
        filters = [
            AdsFilter._filter_by_price_range,
            AdsFilter._filter_by_black_keywords,
            AdsFilter._filter_by_white_keyword,
            AdsFilter._filter_by_address,
            AdsFilter._filter_by_seller,
            AdsFilter._filter_by_recent_time,
            AdsFilter._filter_by_reserve,
            AdsFilter._filter_by_promotion,
        ]
        
        for f in filters:
            if not filtered:
                break
            filtered = f(filtered, config)
            # logger.debug(f"После фильтрации {f.__name__} осталось {len(filtered)}")
            
        return filtered

    @staticmethod
    def _filter_by_price_range(ads: list[Item], config: AvitoConfig) -> list[Item]:
        try:
            return [ad for ad in ads if config.min_price <= ad.priceDetailed.value <= config.max_price]
        except Exception as err:
            logger.debug(f"Ошибка при фильтрации по цене: {err}")
            return ads

    @staticmethod
    def _filter_by_black_keywords(ads: list[Item], config: AvitoConfig) -> list[Item]:
        if not config.keys_word_black_list:
            return ads
        try:
            return [ad for ad in ads if not AdsFilter._is_phrase_in_ads(ad, config.keys_word_black_list)]
        except Exception as err:
            logger.debug(f"Ошибка при проверке по черному списку слов: {err}")
            return ads

    @staticmethod
    def _filter_by_white_keyword(ads: list[Item], config: AvitoConfig) -> list[Item]:
        if not config.keys_word_white_list:
            return ads
        try:
            return [ad for ad in ads if AdsFilter._is_phrase_in_ads(ad, config.keys_word_white_list)]
        except Exception as err:
            logger.debug(f"Ошибка при проверке по белому списку слов: {err}")
            return ads

    @staticmethod
    def _filter_by_address(ads: list[Item], config: AvitoConfig) -> list[Item]:
        if not config.geo:
            return ads
        try:
            return [ad for ad in ads if config.geo.lower() in ad.geo.formattedAddress.lower()]
        except Exception as err:
            logger.debug(f"Ошибка при проверке по адресу: {err}")
            return ads

    @staticmethod
    def _filter_by_seller(ads: list[Item], config: AvitoConfig) -> list[Item]:
        if not config.seller_black_list:
            return ads
        try:
            return [ad for ad in ads if not ad.sellerId or ad.sellerId not in config.seller_black_list]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании черного списка продавцов: {err}")
            return ads

    @staticmethod
    def _filter_by_recent_time(ads: list[Item], config: AvitoConfig) -> list[Item]:
        if not config.max_age:
            return ads
        try:
            return [ad for ad in ads if ad.sortTimeStamp and AdsFilter._is_recent(ad.sortTimeStamp, config.max_age)]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании старых объявлений: {err}")
            return ads

    @staticmethod
    def _filter_by_reserve(ads: list[Item], config: AvitoConfig) -> list[Item]:
        if not config.ignore_reserv:
            return ads
        try:
            return [ad for ad in ads if not ad.isReserved]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании резерва: {err}")
            return ads

    @staticmethod
    def _filter_by_promotion(ads: list[Item], config: AvitoConfig) -> list[Item]:
        AdsFilter._add_promotion_to_ads(ads)
        if not config.ignore_promotion:
            return ads
        try:
            return [ad for ad in ads if not ad.isPromotion]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании продвижения: {err}")
            return ads

    @staticmethod
    def _add_promotion_to_ads(ads: list[Item]):
        for ad in ads:
            ad.isPromotion = any(
                v.get("title") == "Продвинуто"
                for step in (ad.iva or {}).get("DateInfoStep", [])
                for v in step.payload.get("vas", [])
            )

    @staticmethod
    def _is_phrase_in_ads(ad: Item, phrases: list) -> bool:
        full_text_from_ad = (ad.title + " " + ad.description).lower()
        return any(phrase.lower() in full_text_from_ad for phrase in phrases)

    @staticmethod
    def _is_recent(timestamp_ms: int, max_age_seconds: int) -> bool:
        now = datetime.utcnow()
        published_time = datetime.utcfromtimestamp(timestamp_ms / 1000)
        return (now - published_time) <= timedelta(seconds=max_age_seconds)
