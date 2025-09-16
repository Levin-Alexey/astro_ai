#!/usr/bin/env python3
"""
Тест webhook сервера
"""
import requests
import json

def test_webhook():
    """Тестирует webhook сервер"""
    base_url = "https://pay.neyroastro.ru"
    
    print("=== ТЕСТ WEBHOOK СЕРВЕРА ===")
    
    # Тест 1: GET запрос
    print("\n1. Тестирование GET запроса...")
    try:
        response = requests.get(f"{base_url}/webhook", timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Тест 2: POST запрос
    print("\n2. Тестирование POST запроса...")
    try:
        test_data = {
            "event": "payment.succeeded",
            "object": {
                "metadata": {
                    "user_id": "12345",
                    "planet": "sun"
                }
            }
        }
        response = requests.post(
            f"{base_url}/webhook", 
            json=test_data,
            timeout=10
        )
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Тест 3: Health check
    print("\n3. Тестирование health check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # Тест 4: Success page
    print("\n4. Тестирование success page...")
    try:
        response = requests.get(f"{base_url}/webhook/success", timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    test_webhook()
