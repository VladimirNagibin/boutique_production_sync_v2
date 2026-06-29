# Создание таблиц
sql_script_create_table = """
-- Таблица для кодов товаров поставщиков
CREATE TABLE IF NOT EXISTS supplier_product_codes (
    -- Первичный ключ (автоинкремент)
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Код товара у поставщика
    code INTEGER NOT NULL CHECK (code > 0),

    -- Наименование товара поставщика
    name TEXT NOT NULL CHECK (LENGTH(TRIM(name)) > 0),

    -- Группа товаров
    category TEXT,

    -- Подгруппа товаров
    subcategory TEXT,

    -- Идентификатор поставщика
    supplier_id INTEGER NOT NULL,

    -- Уникальность связки (код поставщика + код товара)
    CONSTRAINT unique_supplier_code UNIQUE (code, supplier_id)
);

-- Индекс для быстрого поиска по поставщику и коду
CREATE INDEX IF NOT EXISTS idx_supplier_code
ON supplier_product_codes (supplier_id, code);

-- Индекс для поиска по названию товара
CREATE INDEX IF NOT EXISTS idx_product_name
ON supplier_product_codes (name);

-- Таблица для кодов товаров поставщиков одежды
CREATE TABLE IF NOT EXISTS supplier_clothing_codes (
    -- Первичный ключ (автоинкремент)
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Код товара у поставщика
    code INTEGER NOT NULL CHECK (code > 0),

    -- Наименование товара поставщика
    name TEXT NOT NULL CHECK (LENGTH(TRIM(name)) > 0),

    -- Группа товаров
    category TEXT,

    -- Подгруппа товаров
    subcategory TEXT,

    -- Идентификатор поставщика
    supplier_id INTEGER NOT NULL,

    --Товар сводно
    product_summary TEXT NOT NULL CHECK (LENGTH(TRIM(product_summary)) > 0),

    -- Размер
    size TEXT,

    -- Цвет
    color TEXT,

    -- Строковый код
    supplier_code VARCHAR(255),

    -- Описание
    description TEXT,

    -- Уникальность связки (код поставщика + код товара)
    CONSTRAINT unique_supplier_code UNIQUE (code, supplier_id)
);

-- Индекс для быстрого поиска по поставщику и коду
CREATE INDEX IF NOT EXISTS idx_supplier_code_clothing
ON supplier_product_codes (supplier_id, code);

-- Индекс для поиска по названию товара
CREATE INDEX IF NOT EXISTS idx_product_name_clothing
ON supplier_product_codes (name);


-- Таблица для текущего прайса поставщика
CREATE TABLE IF NOT EXISTS supplier_price (
    -- Первичный ключ (автоинкремент)
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Код товара у поставщика
    code INTEGER NOT NULL CHECK (code > 0),

    -- Наименование товара поставщика
    name TEXT NOT NULL CHECK (LENGTH(TRIM(name)) > 0),

    -- Группа товаров
    category TEXT,

    -- Подгруппа товаров
    subcategory TEXT,

    -- Идентификатор поставщика
    supplier_id INTEGER NOT NULL,

    --Товар сводно
    product_summary TEXT NOT NULL CHECK (LENGTH(TRIM(product_summary)) > 0),

    -- Размер
    size TEXT,

    -- Цвет
    color TEXT,

    -- Цена
    price REAL NOT NULL CHECK (price >= 0),

    -- Уникальность связки (код поставщика + код товара)
    CONSTRAINT unique_supplier_code UNIQUE (code, supplier_id)
);

-- Индекс для быстрого поиска по поставщику и коду
CREATE INDEX IF NOT EXISTS idx_supplier_code
ON supplier_product_codes (supplier_id, code);

-- Индекс для поиска по названию товара
CREATE INDEX IF NOT EXISTS idx_product_name
ON supplier_product_codes (name);

"""
