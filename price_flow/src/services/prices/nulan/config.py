# --- Конфигурация ---
FOLDER_NAME = 'uploads'
TEMP_FOLDER_NAME = 'tmp'

# Сопоставление оригинального имени файла с новым (каноническим) именем
FILENAME_MAPPING = {
    'leggins.xlsx': '19 leggins.xlsx',
    'kolgotki-classica.xlsx': '1 kolgotki.xlsx',
    'kolgotki-detstvo.xlsx': '11 kolgotki det.xlsx',
    'kolgotki-azzuro.xlsx': '1 kolgotki 2.xlsx',
    'korsetnoe.xlsx': '3 korsetnoe(italia,espania).xlsx',
    'beshovnoe.xlsx': '2 intimidea.xlsx',
    'domashka.xlsx': '10 angel stori.xlsx',
    'muzckoe.xlsx': '6 griff muzckoe.xlsx',
    'mitex.xlsx': '7 mitex.xlsx',
    'obuv.xlsx': '17 noskitap.xlsx',
    'kupalniki.xlsx': '8 kypalniki.xlsx',
    'hobbi.xlsx': '16 Nausniki.xlsx',
    'распродажа.xlsx': '15 suvenir.xlsx',
    'OPIUM-sport.xlsx': '14 varezki.xlsx',
    'noski.xlsx': '12 noski.xlsx',
    'zenskie-plavki.xlsx': '5 malemi.xlsx',
    'termobelio.xlsx': '4 termobelio.xlsx',
    'dom-obuv.xlsx': '21 dom.obuv.xlsx',
}

# Параметры обработки товаров (сохранены для совместимости)
PRODUCT_SKIP_HEAD_ROWS = range(7)
PRODUCT_SIGN_COLUMN = 1
PRODUCT_IMAGE_COLUMN = 2
PRODUCT_NAME_COLUMN = 3
PRODUCT_SIZE_RANGE = range(14, 23)
PRODUCT_PRICE_COLUMN = 32
PRODUCT_COLOR_COLUMN = 3
PRODUCT_START_REMAINS_COLUMN = 14
FILE_CHANGE = '11 kolgotki det.xlsx'
