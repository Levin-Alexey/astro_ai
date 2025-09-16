#!/usr/bin/env python3
"""
Проверка работы сервера
"""
import requests
import json

def check_server():
    """Проверяет работу сервера"""
    base_url = "https://pay.neyroastro.ru"
    
    print("=== ПРОВЕРКА СЕРВЕРА ===")
    
    # 1. Health check
    print("\n1. Health check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # 2. Webhook GET
    print("\n2. Webhook GET...")
    try:
        response = requests.get(f"{base_url}/webhook", timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # 3. Webhook POST с тестовыми данными
    print("\n3. Webhook POST...")
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
        response = requests.post(f"{base_url}/webhook", json=test_data, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    check_server()
