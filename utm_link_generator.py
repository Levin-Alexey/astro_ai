"""
Утилита для генерации Deep Links с UTM метками для Telegram бота

Использование:
    python utm_link_generator.py
"""

def generate_utm_link(
    bot_username: str,
    utm_source: str = None,
    utm_medium: str = None,
    utm_campaign: str = None,
    utm_content: str = None,
    utm_term: str = None,
    referral_code: str = None
) -> str:
    """
    Генерирует deep link для Telegram бота с UTM метками
    
    Args:
        bot_username: Имя бота без @
        utm_source: Источник трафика (instagram, facebook, google и т.д.)
        utm_medium: Канал трафика (cpc, social, email и т.д.)
        utm_campaign: Название кампании
        utm_content: Вариант контента
        utm_term: Ключевое слово
        referral_code: Реферальный код (альтернатива UTM меткам)
        
    Returns:
        Готовая ссылка для распространения
    """
    base_url = f"https://t.me/{bot_username}?start="
    
    # Если указан реферальный код, используем его
    if referral_code:
        return f"{base_url}ref_{referral_code}"
    
    # Собираем UTM параметры
    params = []
    
    if utm_source:
        params.append(utm_source)
    if utm_medium:
        params.append(utm_medium)
    if utm_campaign:
        params.append(utm_campaign)
    if utm_content:
        params.append(utm_content)
    if utm_term:
        params.append(utm_term)
    
    if not params:
        return f"https://t.me/{bot_username}"
    
    param_string = "_".join(params)
    return f"{base_url}{param_string}"


def main():
    """Интерактивный генератор ссылок"""
    print("=" * 60)
    print("🔗 Генератор Deep Links с UTM метками для Telegram бота")
    print("=" * 60)
    print()
    
    # Получаем имя бота
    bot_username = input("Введите username бота (без @): ").strip()
    if not bot_username:
        print("❌ Ошибка: необходимо указать username бота")
        return
    
    print()
    print("Выберите тип ссылки:")
    print("1. UTM метки (для рекламных кампаний)")
    print("2. Реферальный код (для партнеров/блогеров)")
    print()
    
    choice = input("Ваш выбор (1 или 2): ").strip()
    
    if choice == "2":
        # Реферальная ссылка
        ref_code = input("Введите реферальный код: ").strip()
        if ref_code:
            link = generate_utm_link(bot_username, referral_code=ref_code)
            print()
            print("✅ Ваша реферальная ссылка:")
            print(link)
    else:
        # UTM метки
        print()
        print("Заполните UTM метки (можно пропустить, нажав Enter):")
        print()
        
        utm_source = input("utm_source (источник, например: instagram, facebook, google): ").strip() or None
        utm_medium = input("utm_medium (канал, например: stories, ads, cpc): ").strip() or None
        utm_campaign = input("utm_campaign (название кампании, например: spring2025): ").strip() or None
        utm_content = input("utm_content (вариант контента, опционально): ").strip() or None
        utm_term = input("utm_term (ключевое слово, опционально): ").strip() or None
        
        link = generate_utm_link(
            bot_username,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term
        )
        
        print()
        print("✅ Ваша UTM ссылка:")
        print(link)
    
    print()
    print("=" * 60)
    
    # Примеры использования
    print()
    print("📚 Примеры популярных ссылок:")
    print()
    examples = [
        ("Instagram Stories", {"utm_source": "instagram", "utm_medium": "stories", "utm_campaign": "promo1"}),
        ("Facebook Ads", {"utm_source": "facebook", "utm_medium": "cpc", "utm_campaign": "spring2025"}),
        ("VK Реклама", {"utm_source": "vk", "utm_medium": "ads", "utm_campaign": "march"}),
        ("YouTube", {"utm_source": "youtube", "utm_medium": "video", "utm_campaign": "review"}),
        ("Блогер Anna", {"referral_code": "anna_instagram"}),
    ]
    
    for name, params in examples:
        example_link = generate_utm_link(bot_username, **params)
        print(f"{name}:")
        print(f"  {example_link}")
        print()


if __name__ == "__main__":
    main()
