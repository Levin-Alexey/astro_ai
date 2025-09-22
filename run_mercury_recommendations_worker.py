#!/usr/bin/env python3
"""
Скрипт для запуска Mercury Recommendations Worker
"""

import subprocess
import sys
import os

def main():
    """Запуск Mercury recommendations worker"""
    
    # Получаем путь к текущей директории
    current_dir = os.path.dirname(os.path.abspath(__file__))
    worker_path = os.path.join(current_dir, "mercury_recommendations_worker.py")
    
    print("🚀 Starting Mercury Recommendations Worker...")
    print(f"📂 Worker path: {worker_path}")
    
    try:
        # Запускаем worker
        subprocess.run([sys.executable, worker_path], check=True)
    except KeyboardInterrupt:
        print("\n⚠️ Mercury Recommendations Worker stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Mercury Recommendations Worker failed with exit code {e.returncode}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error running Mercury Recommendations Worker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()