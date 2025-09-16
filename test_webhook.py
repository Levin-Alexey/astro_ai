#!/usr/bin/env python3
"""
Тест webhook
"""
import requests
import json

def test_webhook():
    """Тестирует webhook"""
    url = "https://pay.neyroastro.ru/webhook"
    
    print("=== ТЕСТ WEBHOOK ===")
    
    # GET запрос
    print("\n1. GET запрос...")
    try:
        response = requests.get(url, timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # POST запрос с payment.succeeded
    print("\n2. POST запрос с payment.succeeded...")
    try:
        data = {
            "event": "payment.succeeded",
            "object": {
                "metadata": {
                    "user_id": "12345",
                    "planet": "sun"
                }
            }
        }
        response = requests.post(url, json=data, timeout=10)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {response.text}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    test_webhook()