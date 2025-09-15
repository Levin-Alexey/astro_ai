-- Миграция для добавления новых столбцов в таблицу predictions
-- Дата: 2024-12-19
-- Описание: Разделяем данные по типам контента для избежания перезаписи

-- Добавляем новые столбцы для разных типов анализа
ALTER TABLE predictions 
ADD COLUMN moon_analysis TEXT,
ADD COLUMN sun_analysis TEXT,
ADD COLUMN mercury_analysis TEXT,
ADD COLUMN venus_analysis TEXT,
ADD COLUMN mars_analysis TEXT,
ADD COLUMN recommendations TEXT,
ADD COLUMN qa_responses TEXT;

-- Делаем content nullable (если еще не nullable)
ALTER TABLE predictions 
ALTER COLUMN content DROP NOT NULL;

-- Добавляем ограничение, что должен быть хотя бы один тип контента
ALTER TABLE predictions 
ADD CONSTRAINT at_least_one_content_type 
CHECK (
    content IS NOT NULL OR 
    moon_analysis IS NOT NULL OR 
    sun_analysis IS NOT NULL OR 
    mercury_analysis IS NOT NULL OR 
    venus_analysis IS NOT NULL OR 
    mars_analysis IS NOT NULL OR 
    recommendations IS NOT NULL OR 
    qa_responses IS NOT NULL
);

-- Комментарии к новым столбцам
COMMENT ON COLUMN predictions.moon_analysis IS 'Анализ Луны (бесплатный)';
COMMENT ON COLUMN predictions.sun_analysis IS 'Анализ Солнца (платный)';
COMMENT ON COLUMN predictions.mercury_analysis IS 'Анализ Меркурия (платный)';
COMMENT ON COLUMN predictions.venus_analysis IS 'Анализ Венеры (платный)';
COMMENT ON COLUMN predictions.mars_analysis IS 'Анализ Марса (платный)';
COMMENT ON COLUMN predictions.recommendations IS 'Рекомендации по темам';
COMMENT ON COLUMN predictions.qa_responses IS 'Ответы на вопросы пользователя';
