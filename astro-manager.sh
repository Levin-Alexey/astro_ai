#!/bin/bash

# Скрипт для перезапуска всех астро-сервисов
# Автор: GitHub Copilot
# Дата: 23.09.2025

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Массив с названиями всех сервисов
SERVICES=(
    "astro-mercury-recommendations-worker.service"
    "astro-mercury-worker.service"
    "astro-question-worker.service"
    "astro-sun-recommendations-worker.service"
    "astro-sun-worker.service"
    "astro-worker.service"
    "rec-worker.service"
    "venus-recommendations-worker.service"
    "venus-worker.service"
)

echo -e "${BLUE}🚀 Скрипт перезапуска астро-сервисов${NC}"
echo -e "${BLUE}====================================${NC}"
echo ""

# Функция для проверки статуса сервиса
check_service_status() {
    local service=$1
    if systemctl is-active --quiet "$service"; then
        echo -e "${GREEN}✅ $service - активен${NC}"
        return 0
    else
        echo -e "${RED}❌ $service - неактивен${NC}"
        return 1
    fi
}

# Функция для остановки сервиса
stop_service() {
    local service=$1
    echo -e "${YELLOW}🛑 Останавливаю $service...${NC}"
    sudo systemctl stop "$service"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $service остановлен${NC}"
    else
        echo -e "${RED}❌ Ошибка остановки $service${NC}"
    fi
}

# Функция для запуска сервиса
start_service() {
    local service=$1
    echo -e "${YELLOW}🟢 Запускаю $service...${NC}"
    sudo systemctl start "$service"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $service запущен${NC}"
    else
        echo -e "${RED}❌ Ошибка запуска $service${NC}"
    fi
}

# Функция для перезапуска сервиса
restart_service() {
    local service=$1
    echo -e "${YELLOW}🔄 Перезапускаю $service...${NC}"
    sudo systemctl restart "$service"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $service перезапущен${NC}"
        return 0
    else
        echo -e "${RED}❌ Ошибка перезапуска $service${NC}"
        return 1
    fi
}

# Показать меню
show_menu() {
    echo ""
    echo -e "${BLUE}Выберите действие:${NC}"
    echo "1) Проверить статус всех сервисов"
    echo "2) Перезапустить все сервисы"
    echo "3) Остановить все сервисы"
    echo "4) Запустить все сервисы"
    echo "5) Показать логи всех сервисов"
    echo "6) Перезапустить конкретный сервис"
    echo "7) Показать статус в реальном времени"
    echo "8) 🚨 ЭКСТРЕННАЯ ОСТАНОВКА (решить конфликт ботов)"
    echo "9) Проверить системные ресурсы"
    echo "0) Выход"
    echo ""
    read -p "Введите номер действия: " choice
}

# Проверка статуса всех сервисов
check_all_status() {
    echo -e "${BLUE}📊 Проверяю статус всех сервисов...${NC}"
    echo ""
    
    local active_count=0
    local total_count=${#SERVICES[@]}
    
    for service in "${SERVICES[@]}"; do
        if check_service_status "$service"; then
            ((active_count++))
        fi
    done
    
    echo ""
    echo -e "${BLUE}📈 Сводка: ${GREEN}$active_count${NC}/${BLUE}$total_count${NC} сервисов активны"
}

# Перезапуск всех сервисов
restart_all() {
    echo -e "${BLUE}🔄 Перезапускаю все сервисы...${NC}"
    echo ""
    
    local success_count=0
    local total_count=${#SERVICES[@]}
    
    for service in "${SERVICES[@]}"; do
        if restart_service "$service"; then
            ((success_count++))
        fi
        echo ""
    done
    
    echo -e "${BLUE}📈 Результат: ${GREEN}$success_count${NC}/${BLUE}$total_count${NC} сервисов успешно перезапущены"
}

# Остановка всех сервисов
stop_all() {
    echo -e "${BLUE}🛑 Останавливаю все сервисы...${NC}"
    echo ""
    
    for service in "${SERVICES[@]}"; do
        stop_service "$service"
        echo ""
    done
}

# Запуск всех сервисов
start_all() {
    echo -e "${BLUE}🟢 Запускаю все сервисы...${NC}"
    echo ""
    
    for service in "${SERVICES[@]}"; do
        start_service "$service"
        echo ""
    done
}

# Показать логи всех сервисов
show_logs() {
    echo -e "${BLUE}📋 Последние логи всех сервисов:${NC}"
    echo ""
    
    for service in "${SERVICES[@]}"; do
        echo -e "${YELLOW}--- Логи $service ---${NC}"
        sudo journalctl -u "$service" -n 5 --no-pager
        echo ""
    done
}

# Перезапуск конкретного сервиса
restart_specific() {
    echo -e "${BLUE}Выберите сервис для перезапуска:${NC}"
    echo ""
    
    for i in "${!SERVICES[@]}"; do
        echo "$((i+1))) ${SERVICES[$i]}"
    done
    
    echo ""
    read -p "Введите номер сервиса: " service_num
    
    if [[ "$service_num" =~ ^[0-9]+$ ]] && [ "$service_num" -ge 1 ] && [ "$service_num" -le "${#SERVICES[@]}" ]; then
        selected_service="${SERVICES[$((service_num-1))]}"
        restart_service "$selected_service"
    else
        echo -e "${RED}❌ Неверный номер сервиса${NC}"
    fi
}

# Показать статус в реальном времени
show_realtime_status() {
    echo -e "${BLUE}📊 Статус сервисов в реальном времени (Ctrl+C для выхода):${NC}"
    echo ""
    
    while true; do
        clear
        echo -e "${BLUE}🚀 Астро-сервисы - $(date)${NC}"
        echo -e "${BLUE}================================${NC}"
        echo ""
        
        for service in "${SERVICES[@]}"; do
            check_service_status "$service"
        done
        
        echo ""
        echo -e "${YELLOW}Обновление каждые 5 секунд...${NC}"
        sleep 5
    done
}

# Экстренная остановка всех процессов
emergency_stop() {
    echo -e "${RED}🚨 ЭКСТРЕННАЯ ОСТАНОВКА ВСЕХ ПРОЦЕССОВ!${NC}"
    echo ""
    
    # Останавливаем все сервисы
    echo -e "${YELLOW}Останавливаю все сервисы...${NC}"
    for service in "${SERVICES[@]}"; do
        sudo systemctl stop "$service" 2>/dev/null
        echo -e "${YELLOW}Остановлен: $service${NC}"
    done
    
    echo ""
    echo -e "${YELLOW}Убиваю все Python процессы связанные с ботом...${NC}"
    
    # Находим и убиваем все процессы Python с астро
    sudo pkill -f "python.*astro" 2>/dev/null
    sudo pkill -f "python.*bot" 2>/dev/null
    sudo pkill -f "python.*worker" 2>/dev/null
    sudo pkill -f "python.*main.py" 2>/dev/null
    
    sleep 2
    
    echo ""
    echo -e "${GREEN}✅ Экстренная остановка завершена!${NC}"
    echo -e "${BLUE}Теперь можно безопасно запустить сервисы заново.${NC}"
}

# Проверка системных ресурсов
check_system_resources() {
    echo -e "${BLUE}🔍 Проверка системных ресурсов...${NC}"
    echo ""
    
    # Использование CPU и памяти
    echo -e "${YELLOW}📊 Использование ресурсов:${NC}"
    echo "CPU и память:"
    top -bn1 | grep "Cpu\|Mem" | head -2
    echo ""
    
    # Python процессы
    echo -e "${YELLOW}🐍 Python процессы:${NC}"
    ps aux | grep python | grep -v grep | head -10
    echo ""
    
    # Сетевые соединения
    echo -e "${YELLOW}🌐 Сетевые соединения (порт 8443 для бота):${NC}"
    sudo netstat -tulpn | grep :8443 2>/dev/null || echo "Порт 8443 свободен"
    echo ""
    
    # Место на диске
    echo -e "${YELLOW}💾 Место на диске:${NC}"
    df -h | head -5
    echo ""
    
    # Логи ошибок за последний час
    echo -e "${YELLOW}🚨 Последние ошибки в логах:${NC}"
    sudo journalctl --priority=err --since "1 hour ago" | tail -5
}

# Основной цикл
main() {
    while true; do
        show_menu
        
        case $choice in
            1)
                check_all_status
                ;;
            2)
                restart_all
                ;;
            3)
                stop_all
                ;;
            4)
                start_all
                ;;
            5)
                show_logs
                ;;
            6)
                restart_specific
                ;;
            7)
                show_realtime_status
                ;;
            8)
                emergency_stop
                ;;
            9)
                check_system_resources
                ;;
            0)
                echo -e "${GREEN}👋 До свидания!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}❌ Неверный выбор. Попробуйте снова.${NC}"
                ;;
        esac
        
        echo ""
        read -p "Нажмите Enter для продолжения..."
    done
}

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Этот скрипт требует права root (sudo)${NC}"
    echo "Запустите: sudo ./astro-manager.sh"
    exit 1
fi

# Запуск основной функции
main