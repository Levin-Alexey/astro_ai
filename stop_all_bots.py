#!/usr/bin/env python3
"""
Остановка всех процессов бота
"""
import subprocess
import sys

def stop_all_bots():
    """Останавливает все процессы бота"""
    print("=== ОСТАНОВКА ВСЕХ ПРОЦЕССОВ БОТА ===")
    
    try:
        # Находим все процессы с main.py или run_with_webhook.py
        result = subprocess.run(
            ["ps", "aux"], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            bot_processes = []
            
            for line in lines:
                if 'main.py' in line or 'run_with_webhook.py' in line:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        bot_processes.append(pid)
                        print(f"Найден процесс бота: PID {pid}")
            
            if bot_processes:
                print(f"\nОстанавливаем {len(bot_processes)} процессов...")
                for pid in bot_processes:
                    try:
                        subprocess.run(["kill", "-9", pid], check=True)
                        print(f"Процесс {pid} остановлен")
                    except subprocess.CalledProcessError as e:
                        print(f"Ошибка при остановке процесса {pid}: {e}")
            else:
                print("Процессы бота не найдены")
        else:
            print("Ошибка при получении списка процессов")
            
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    stop_all_bots()
