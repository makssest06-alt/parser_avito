import uuid
import logging
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.shop_id = YOOKASSA_SHOP_ID
        self.secret_key = YOOKASSA_SECRET_KEY
        
        # Проверяем наличие учетных данных
        if not self.shop_id or not self.secret_key:
            logger.warning("YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не установлены. Платежи будут работать в тестовом режиме.")
            self.test_mode = True
        else:
            self.test_mode = False
            try:
                from yookassa import Configuration
                Configuration.account_id = self.shop_id
                Configuration.secret_key = self.secret_key
                logger.info("Конфигурация ЮKassa успешно установлена")
            except Exception as e:
                logger.error(f"Ошибка настройки ЮKassa: {e}")
                self.test_mode = True
        
    def create_payment(self, amount: float, description: str, user_id: int, plan_id: str):
        """Создает платеж в ЮKassa"""
        try:
            if self.test_mode:
                return self._create_test_payment(amount, description, user_id, plan_id)
                
            from yookassa import Payment
            from yookassa.domain.models.currency import Currency
            
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
                    "return_url": f"https://t.me/{self._get_bot_username()}"
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
            # Возвращаем тестовый платеж для демонстрации
            return self._create_test_payment(amount, description, user_id, plan_id)
    
    def _create_test_payment(self, amount: float, description: str, user_id: int, plan_id: str):
        """Создает тестовый платеж для демонстрации"""
        class TestPayment:
            def __init__(self, amount, description, user_id, plan_id):
                self.id = f"test_payment_{uuid.uuid4()}"
                self.status = "pending"
                self.confirmation = type('obj', (object,), {
                    'confirmation_url': f"https://example.com/test_payment?amount={amount}&user={user_id}"
                })()
        
        logger.info(f"Создан тестовый платеж для пользователя {user_id} (сумма: {amount} руб.)")
        return TestPayment(amount, description, user_id, plan_id)
    
    def _get_bot_username(self):
        """Получает username бота"""
        try:
            from config import BOT_TOKEN
            # В реальном боте нужно получить username через getMe
            return "your_bot"
        except:
            return "your_bot_username"
    
    def check_payment_status(self, payment_id: str):
        """Проверяет статус платежа"""
        try:
            # Для тестовых платежей
            if payment_id.startswith('test_payment_'):
                # В тестовом режиме считаем, что платеж успешен
                return 'succeeded'
                
            from yookassa import Payment
            payment = Payment.find_one(payment_id)
            return payment.status
        except Exception as e:
            logger.error(f"Ошибка проверки статуса платежа {payment_id}: {e}")
            # В случае ошибки считаем платеж ожидающим
            return 'pending'

payment_service = PaymentService()
