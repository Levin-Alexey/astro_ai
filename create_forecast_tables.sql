-- Таблица для управления подписками на персональные прогнозы
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    start_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_date TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Индексы для таблицы subscriptions
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_end_date ON subscriptions(end_date);
CREATE INDEX IF NOT EXISTS idx_subscriptions_is_active ON subscriptions(is_active);

-- Таблица для хранения платежей по подпискам на персональные прогнозы
CREATE TABLE IF NOT EXISTS subscription_payments (
    payment_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount_kopecks BIGINT NOT NULL,
    status payment_status NOT NULL DEFAULT 'pending', -- Переиспользуем существующий ENUM
    external_payment_id TEXT,
    payment_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Индексы для таблицы subscription_payments
CREATE INDEX IF NOT EXISTS idx_sub_payments_user_id ON subscription_payments(user_id);
CREATE INDEX IF NOT EXISTS idx_sub_payments_status ON subscription_payments(status);
CREATE INDEX IF NOT EXISTS idx_sub_payments_external_id ON subscription_payments(external_payment_id);

-- Таблица для хранения сгенерированных ежедневных прогнозов
CREATE TABLE IF NOT EXISTS daily_forecasts (
    forecast_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, date) -- Уникальный прогноз на день для пользователя
);

-- Индексы для таблицы daily_forecasts
CREATE INDEX IF NOT EXISTS idx_daily_forecasts_user_id ON daily_forecasts(user_id);
CREATE INDEX IF NOT EXISTS idx_daily_forecasts_date ON daily_forecasts(date);