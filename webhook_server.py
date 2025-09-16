import asyncio
import json
import logging
from aiohttp import web
from aiohttp.web import Request, Response
from payment_handler import payment_handler

logger = logging.getLogger(__name__)


class WebhookServer:
    """Сервер для обработки webhook от ЮKassa"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        """Настраивает маршруты"""
        self.app.router.add_post(
            '/webhook/payment', self.handle_payment_webhook
        )
        self.app.router.add_get('/webhook/success', self.payment_success)
        self.app.router.add_get('/health', self.health_check)
    
    async def handle_payment_webhook(self, request: Request) -> Response:
        """Обрабатывает webhook от ЮKassa"""
        try:
            # Получаем тело запроса
            body = await request.text()
            
            # Получаем заголовки (ЮKassa использует разные заголовки)
            signature = (
                request.headers.get('HTTP_AUTHORIZATION', '') or
                request.headers.get('Authorization', '') or
                request.headers.get('X-YooMoney-Signature', '')
            )
            
            # Проверяем подпись
            if not payment_handler or not payment_handler.verify_webhook(body, signature):
                logger.warning("Неверная подпись webhook")
                return Response(status=400, text="Invalid signature")
            
            # Парсим JSON
            try:
                webhook_data = json.loads(body)
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON: {e}")
                return Response(status=400, text="Invalid JSON")
            
            # Обрабатываем платеж
            if payment_handler:
                success = await payment_handler.process_payment_webhook(webhook_data)
            else:
                success = False
            
            if success:
                logger.info("Webhook успешно обработан")
                return Response(status=200, text="OK")
            else:
                logger.warning("Webhook не обработан")
                return Response(status=200, text="Not processed")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке webhook: {e}")
            return Response(status=500, text="Internal server error")

    async def payment_success(self, request: Request) -> Response:
        """Страница успешной оплаты"""
        return Response(
            status=200, 
            text="Платеж успешно обработан! Вернитесь в Telegram бот.",
            content_type="text/html; charset=utf-8"
        )

    async def health_check(self, request: Request) -> Response:
        """Проверка здоровья сервера"""
        return Response(status=200, text="OK")
    
    async def start(self):
        """Запускает сервер"""
        logger.info(f"Запуск webhook сервера на {self.host}:{self.port}")
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("Webhook сервер запущен")
        return runner


async def start_webhook_server():
    """Запускает webhook сервер"""
    server = WebhookServer()
    runner = await server.start()
    return runner

if __name__ == "__main__":
    # Для тестирования webhook сервера отдельно
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_webhook_server())
