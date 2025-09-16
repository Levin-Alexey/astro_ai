#!/usr/bin/env python3
"""
Тест webhook с правильным форматом payment.succeeded
"""
import requests
import json

def test_payment_webhook():
    """Тестирует webhook с событием payment.succeeded"""
    url = "https://pay.neyroastro.ru/webhook"
    
    print("=== ТЕСТ WEBHOOK С PAYMENT.SUCCEEDED ===")
    
    # Правильный формат webhook от ЮKassa
    webhook_data = {
        "type": "notification",
        "event": "payment.succeeded",
        "object": {
            "id": "2c4d4b4a-0002-0001-0000-000000000000",
            "status": "succeeded",
            "paid": True,
            "amount": {
                "value": "10.00",
                "currency": "RUB"
            },
            "created_at": "2025-09-16T08:30:00.000Z",
            "description": "Астрологический разбор ☀️ Солнце",
            "metadata": {
                "user_id": "12345",
                "planet": "sun"
            },
            "recipient": {
                "account_id": "1139243",
                "gateway_id": "yookassa"
            }
        }
    }
    
    print(f"Отправляем webhook: {json.dumps(webhook_data, indent=2)}")
    
    try:
        response = requests.post(
            url, 
            json=webhook_data,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'YooKassa-Webhook/1.0'
            },
            timeout=10
        )
        
        print(f"\nОтвет сервера:")
        print(f"Статус: {response.status_code}")
        print(f"Заголовки: {dict(response.headers)}")
        print(f"Тело ответа: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook обработан успешно!")
        else:
            print("❌ Ошибка при обработке webhook")
            
    except Exception as e:
        print(f"❌ Ошибка при отправке запроса: {e}")

def test_webhook_get():
    """Тестирует GET запрос к webhook"""
    url = "https://pay.neyroastro.ru/webhook"
    
    print("\n=== ТЕСТ GET ЗАПРОСА ===")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
        
        if response.status_code == 200:
            print("✅ GET запрос работает!")
        else:
            print("❌ Ошибка при GET запросе")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_webhook_get()
    test_payment_webhook()
