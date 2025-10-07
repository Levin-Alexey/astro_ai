# UTM Метки и Отслеживание Источников Трафика

## Описание

Система автоматически собирает UTM метки и реферальные коды при первом запуске бота пользователем. Это позволяет отслеживать эффективность рекламных кампаний и источники трафика.

## Формат Deep Links

### 1. UTM Метки

Формат ссылки:
```
https://t.me/ваш_бот?start=SOURCE_MEDIUM_CAMPAIGN_CONTENT_TERM
```

Параметры разделяются символом подчеркивания `_` в следующем порядке:
1. **utm_source** - источник трафика (google, facebook, instagram, vk и т.д.)
2. **utm_medium** - канал трафика (cpc, social, email, banner и т.д.)
3. **utm_campaign** - название кампании
4. **utm_content** - вариант объявления/контента (опционально)
5. **utm_term** - ключевое слово (опционально)

#### Примеры:

**Минимальная ссылка (только источник):**
```
https://t.me/ваш_бот?start=instagram
```
Сохранится: `utm_source = "instagram"`

**Ссылка с источником и каналом:**
```
https://t.me/ваш_бот?start=instagram_stories
```
Сохранится:
- `utm_source = "instagram"`
- `utm_medium = "stories"`

**Полная ссылка с кампанией:**
```
https://t.me/ваш_бот?start=instagram_stories_spring2025
```
Сохранится:
- `utm_source = "instagram"`
- `utm_medium = "stories"`
- `utm_campaign = "spring2025"`

**Максимально подробная ссылка:**
```
https://t.me/ваш_бот?start=google_cpc_spring2025_banner1_astrology
```
Сохранится:
- `utm_source = "google"`
- `utm_medium = "cpc"`
- `utm_campaign = "spring2025"`
- `utm_content = "banner1"`
- `utm_term = "astrology"`

### 2. Реферальные Коды

Формат ссылки:
```
https://t.me/ваш_бот?start=ref_КОД
```

#### Примеры:

```
https://t.me/ваш_бот?start=ref_user123
```
Сохранится: `referral_code = "user123"`

```
https://t.me/ваш_бот?start=ref_influencer_anna
```
Сохранится: `referral_code = "influencer_anna"`

## Примеры Использования по Платформам

### Instagram Stories/Posts
```
https://t.me/ваш_бот?start=instagram_stories_march2025
```

### Facebook Ads
```
https://t.me/ваш_бот?start=facebook_cpc_astro_campaign_ad1
```

### VK Реклама
```
https://t.me/ваш_бот?start=vk_ads_spring2025_banner
```

### YouTube Описание
```
https://t.me/ваш_бот?start=youtube_video_march2025
```

### Email Рассылка
```
https://t.me/ваш_бот?start=email_newsletter_weekly
```

### Блогер/Инфлюенсер
```
https://t.me/ваш_бот?start=ref_blogger_maria
```

## Хранение Данных

### Поля в базе данных (таблица `users`):

- `utm_source` (TEXT) - источник трафика
- `utm_medium` (TEXT) - канал трафика
- `utm_campaign` (TEXT) - название кампании
- `utm_content` (TEXT) - вариант контента
- `utm_term` (TEXT) - ключевое слово
- `referral_code` (TEXT) - реферальный код

### Правила сохранения:

1. **Новый пользователь** - все UTM метки сохраняются при первом запуске
2. **Существующий пользователь** - UTM метки НЕ перезаписываются (сохраняется источник первого прихода)
3. Если пользователь повторно запустит бота с новыми UTM метками, они будут проигнорированы

## SQL Запросы для Аналитики

### Количество пользователей по источникам:
```sql
SELECT 
    utm_source,
    COUNT(*) as users_count
FROM users
WHERE utm_source IS NOT NULL
GROUP BY utm_source
ORDER BY users_count DESC;
```

### Эффективность кампаний:
```sql
SELECT 
    utm_source,
    utm_campaign,
    COUNT(*) as users_count,
    COUNT(CASE WHEN EXISTS (
        SELECT 1 FROM planet_payments pp 
        WHERE pp.user_id = users.user_id 
        AND pp.status = 'completed'
    ) THEN 1 END) as paid_users
FROM users
WHERE utm_campaign IS NOT NULL
GROUP BY utm_source, utm_campaign
ORDER BY paid_users DESC;
```

### Конверсия по источникам:
```sql
SELECT 
    utm_source,
    COUNT(DISTINCT users.user_id) as total_users,
    COUNT(DISTINCT CASE 
        WHEN pp.status = 'completed' THEN users.user_id 
    END) as paid_users,
    ROUND(
        COUNT(DISTINCT CASE WHEN pp.status = 'completed' THEN users.user_id END)::numeric / 
        COUNT(DISTINCT users.user_id) * 100, 
        2
    ) as conversion_rate
FROM users
LEFT JOIN planet_payments pp ON users.user_id = pp.user_id
WHERE utm_source IS NOT NULL
GROUP BY utm_source
ORDER BY conversion_rate DESC;
```

### Реферальная статистика:
```sql
SELECT 
    referral_code,
    COUNT(*) as users_count,
    COUNT(CASE WHEN EXISTS (
        SELECT 1 FROM planet_payments pp 
        WHERE pp.user_id = users.user_id 
        AND pp.status = 'completed'
    ) THEN 1 END) as paid_users
FROM users
WHERE referral_code IS NOT NULL
GROUP BY referral_code
ORDER BY users_count DESC;
```

## Логирование

Система автоматически логирует:
- Новых пользователей с UTM метками
- Обновление UTM меток для существующих пользователей
- Реферальные коды

Примеры логов:
```
INFO - UTM метки: {'utm_source': 'instagram', 'utm_medium': 'stories', 'utm_campaign': 'spring2025'}
INFO - Реферальный код: user123
INFO - Новый пользователь 123456789 создан с UTM: {'utm_source': 'instagram'}
INFO - Существующий пользователь 123456789, UTM обновлены: {'utm_source': 'facebook'}
```

## Рекомендации

1. **Используйте осмысленные названия** - избегайте случайных кодов
2. **Будьте последовательны** - используйте единый формат для одинаковых источников
3. **Не делайте ссылки слишком длинными** - Telegram может обрезать их
4. **Тестируйте ссылки** перед запуском кампании
5. **Документируйте коды** - ведите таблицу соответствия кодов и кампаний

## Примеры Кодов для Разных Каналов

| Канал | Пример кода | Ссылка |
|-------|-------------|--------|
| Instagram Stories | `instagram_stories_promo1` | `?start=instagram_stories_promo1` |
| Facebook Ads | `facebook_ads_spring_banner` | `?start=facebook_ads_spring_banner` |
| VK Реклама | `vk_ads_march_post` | `?start=vk_ads_march_post` |
| YouTube | `youtube_video_review` | `?start=youtube_video_review` |
| Email | `email_newsletter_weekly` | `?start=email_newsletter_weekly` |
| Блогер Anna | `ref_anna` | `?start=ref_anna` |
| Блогер Maria | `ref_maria_instagram` | `?start=ref_maria_instagram` |
