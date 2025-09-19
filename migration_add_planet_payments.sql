-- Миграция для создания таблицы planet_payments
-- Дата: 2024-12-19
-- Описание: Создаем таблицу для отслеживания платежей за планеты

-- Создаем ENUM для типов платежей
CREATE TYPE payment_type AS ENUM ('single_planet', 'all_planets');

-- Создаем ENUM для статусов платежей
CREATE TYPE payment_status AS ENUM ('pending', 'completed', 'failed', 'refunded');

-- Создаем таблицу planet_payments
CREATE TABLE planet_payments (
    payment_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    payment_type payment_type NOT NULL,
    planet planet NULL, -- NULL для all_planets
    status payment_status NOT NULL DEFAULT 'pending',
    amount_kopecks BIGINT NOT NULL,
    external_payment_id TEXT,
    payment_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    notes TEXT
);

-- Добавляем ограничения
ALTER TABLE planet_payments 
ADD CONSTRAINT single_planet_must_have_planet 
CHECK (
    (payment_type = 'all_planets') OR 
    (payment_type = 'single_planet' AND planet IS NOT NULL)
);

ALTER TABLE planet_payments 
ADD CONSTRAINT amount_positive 
CHECK (amount_kopecks > 0);

ALTER TABLE planet_payments 
ADD CONSTRAINT completed_must_have_completion_time 
CHECK (
    (status != 'completed') OR 
    (status = 'completed' AND completed_at IS NOT NULL)
);

-- Создаем индексы для оптимизации
CREATE INDEX planet_payments_user_id_idx ON planet_payments(user_id);
CREATE INDEX planet_payments_type_idx ON planet_payments(payment_type);
CREATE INDEX planet_payments_planet_idx ON planet_payments(planet);
CREATE INDEX planet_payments_status_idx ON planet_payments(status);
CREATE INDEX planet_payments_created_at_idx ON planet_payments(created_at DESC);
CREATE INDEX planet_payments_external_id_idx ON planet_payments(external_payment_id);

-- Комментарии к таблице и столбцам
COMMENT ON TABLE planet_payments IS 'Таблица платежей за астрологические разборы планет';
COMMENT ON COLUMN planet_payments.payment_id IS 'Уникальный ID платежа';
COMMENT ON COLUMN planet_payments.user_id IS 'ID пользователя из таблицы users';
COMMENT ON COLUMN planet_payments.payment_type IS 'Тип платежа: за одну планету или за все сразу';
COMMENT ON COLUMN planet_payments.planet IS 'Планета (заполняется только для single_planet)';
COMMENT ON COLUMN planet_payments.status IS 'Статус платежа';
COMMENT ON COLUMN planet_payments.amount_kopecks IS 'Сумма платежа в копейках';
COMMENT ON COLUMN planet_payments.external_payment_id IS 'ID платежа в платежной системе (YooKassa)';
COMMENT ON COLUMN planet_payments.payment_url IS 'URL для оплаты';
COMMENT ON COLUMN planet_payments.created_at IS 'Время создания платежа';
COMMENT ON COLUMN planet_payments.completed_at IS 'Время завершения платежа';
COMMENT ON COLUMN planet_payments.notes IS 'Дополнительные заметки';
