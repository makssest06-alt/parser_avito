import uuid
from yookassa import Payment
from yookassa.domain.models.currency import Currency
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
import logging

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.shop_id = YOOKASSA_SHOP_ID
        self.secret_key = YOOKASSA_SECRET_KEY
        
    def create_payment(self, amount: float, description: str, user_id: int, plan_id: str):
        """Создает платеж в ЮKassa"""
        try:
            # Генерируем уникальный idempotence_key
            idempotence_key = str(uuid.uuid4())
            
            # Создаем платеж
            payment = Payment.create({
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": Currency.RUB
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/your_bot_username"  # Замените на username вашего бота
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": user_id,
                    "plan_id": plan_id
                }
            }, idempotence_key)
            
            logger.info(f"Создан платеж {payment.id} для пользователя {user_id}")
            return payment
        except Exception as e:
            logger.error(f"Ошибка создания платежа: {e}")
            return None
    
    def check_payment_status(self, payment_id: str):
        """Проверяет статус платежа"""
        try:
            payment = Payment.find_one(payment_id)
            return payment.status
        except Exception as e:
            logger.error(f"Ошибка проверки статуса платежа {payment_id}: {e}")
            return None

payment_service = PaymentService()
