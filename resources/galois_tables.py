# resources/galois_tables.py

EXP_TABLE: list[int] = [0] * 512  # Антилогарифмы (дублируем для избежания модуля)
LOG_TABLE: list[int] = [0] * 256   # Логарифмы

def generate_galois_tables() -> None:
    """
    Генерирует таблицы EXP и LOG для поля GF(256) с примитивным многочленом x^8 + x^4 + x^3 + x^2 + 1 (0x11d).
    Заполняет глобальные списки EXP_TABLE и LOG_TABLE.
    """
    x = 1
    for i in range(0, 255):
        EXP_TABLE[i] = x
        LOG_TABLE[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    
    # Дублируем таблицу EXP для упрощения вычислений (избавляемся от % 255 при сложении степеней)
    for i in range(255, 512):
        EXP_TABLE[i] = EXP_TABLE[i - 255]

# Генерируем таблицы сразу при импорте модуля
generate_galois_tables()