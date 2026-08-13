# core/encoder.py

from typing import List, Tuple, Literal, Union
import re
from resources.version_tables import DATA_LENGTH_FIELD_SIZE, MAX_DATA_CAPACITY_BYTES

Level = Literal["L", "M", "Q", "H"]
Mode = Literal["numeric", "alphanumeric", "byte", "kanji"]

# Таблица значений для буквенно-цифрового режима (A-Z, 0-9 и спецсимволы)
ALPHANUMERIC_TABLE = {
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    'A': 10, 'B': 11, 'C': 12, 'D': 13, 'E': 14, 'F': 15, 'G': 16, 'H': 17, 'I': 18, 'J': 19,
    'K': 20, 'L': 21, 'M': 22, 'N': 23, 'O': 24, 'P': 25, 'Q': 26, 'R': 27, 'S': 28, 'T': 29,
    'U': 30, 'V': 31, 'W': 32, 'X': 33, 'Y': 34, 'Z': 35, ' ': 36, '$': 37, '%': 38, '*': 39,
    '+': 40, '-': 41, '.': 42, '/': 43, ':': 44
}

# Обратная таблица для поиска символа по значению (используется редко, но полезна)
ALPHANUMERIC_REVERSE = {v: k for k, v in ALPHANUMERIC_TABLE.items()}


def _get_mode_indicator(mode: Mode) -> str:
    """Возвращает 4-битный индикатор режима."""
    indicators = {
        'numeric': '0001',
        'alphanumeric': '0010',
        'byte': '0100',
        'kanji': '1000'
    }
    return indicators[mode]


def _get_char_count_indicator_length(version: int, mode: Mode) -> int:
    """Определяет длину поля количества символов в битах"""
    for version_range, length in DATA_LENGTH_FIELD_SIZE[mode].items():
        if version in version_range:
            return length
    # Для версий выше 40 (теоретически) или ошибок
    raise ValueError(f"Unsupported QR version: {version}")


def encode_numeric(data: str) -> str:
    """Кодирует цифровую строку. 3 цифры -> 10 бит, 2 цифры -> 7 бит, 1 цифра -> 4 бита."""
    bit_string = ""
    # Разбиваем на группы по 3 символа
    for i in range(0, len(data), 3):
        chunk = data[i:i+3]
        if len(chunk) == 3:
            value = int(chunk)
            bit_string += f"{value:010b}"
        elif len(chunk) == 2:
            value = int(chunk)
            bit_string += f"{value:07b}"
        elif len(chunk) == 1:
            value = int(chunk)
            bit_string += f"{value:04b}"
    return bit_string


def encode_alphanumeric(data: str) -> str:
    """Кодирует буквенно-цифровую строку. 2 символа -> 11 бит, 1 символ -> 6 бит."""
    bit_string = ""
    # Разбиваем на группы по 2 символа
    for i in range(0, len(data), 2):
        chunk = data[i:i+2].upper()
        if len(chunk) == 2:
            value = ALPHANUMERIC_TABLE[chunk[0]] * 45 + ALPHANUMERIC_TABLE[chunk[1]]
            bit_string += f"{value:011b}"
        elif len(chunk) == 1:
            value = ALPHANUMERIC_TABLE[chunk]
            bit_string += f"{value:06b}"
    return bit_string


def encode_byte(data: str) -> Tuple[bytes, str]:
    """Кодирует строку в байты (UTF-8) и возвращает битовую строку."""
    byte_data = data.encode('utf-8')
    bit_string = ''.join(f"{byte:08b}" for byte in byte_data)
    return byte_data, bit_string


def _choose_segment_mode(text: str) -> Mode:
    """Определяет наиболее эффективный режим для сегмента текста."""
    if re.fullmatch(r'\d+', text):
        return 'numeric'
    if re.fullmatch(r'[A-Z0-9 $%*+\-./:]+', text, re.IGNORECASE):
        return 'alphanumeric'
    # Для кириллицы и прочих символов всегда используем byte
    return 'byte'


def _estimate_segment_bits(version: int, mode: Mode, data_len: int) -> int:
    """Оценивает длину сегмента в битах (индикатор + счетчик + данные)."""
    indicator = 4
    count_indicator = _get_char_count_indicator_length(version, mode)
    
    if mode == 'numeric':
        data_bits = (data_len * 10) // 3 + (4 if data_len % 3 == 1 else 7 if data_len % 3 == 2 else 0)
    elif mode == 'alphanumeric':
        data_bits = (data_len * 11) // 2 + (6 if data_len % 2 == 1 else 0)
    elif mode == 'byte':
        data_bits = data_len * 8
    elif mode == 'kanji':
        data_bits = data_len * 13
    else:
        data_bits = 0
        
    return indicator + count_indicator + data_bits


def _select_best_version(data: str, level: Level) -> int:
    """Выбирает минимальную версию QR-кода, способную вместить данные."""
    # Пробуем версии с 1 по 40
    for version in range(1, 41):
        capacity_bytes = MAX_DATA_CAPACITY_BYTES[level][version]
        
        # Быстрая оценка: если длина строки в байтах (UTF-8) больше емкости, пропускаем
        # Это грубое исключение, точный расчет ниже
        if len(data.encode('utf-8')) > capacity_bytes * 1.2: 
            continue

        # Точный расчет битового потока с заголовками
        # Для упрощения здесь предполагаем один сегмент, но логика поддерживает и смешанный
        mode = _choose_segment_mode(data)
        required_bits = _estimate_segment_bits(version, mode, len(data))
        
        # Добавляем 4 бита терминатора (стандартно) и паддинг до байта
        total_bits_with_terminator = required_bits + 4
        
        if total_bits_with_terminator <= capacity_bytes * 8:
            return version
            
    raise ValueError("Data too large for Version 40 with current error correction level.")


def encode_data(data: str, level: Level) -> Tuple[int, str]:
    """
    Основной входной метод кодирования.
    Реализует выбор режима, смешанное кодирование (Mixed Mode), добавление заголовка,
    индикатора количества данных, терминатора и байтов заполнения (Padding).
    
    Возвращает:
        tuple: (выбранная_версия, итоговая_битовая_строка)
    """
    version = _select_best_version(data, level)
    
    bit_stream = ""
    segments = []
    
    # --- Реализация смешанного кодирования (Mixed Mode) ---
    # Алгоритм: идем по строке, пока символы подходят под текущий режим.
    # Как только встречаем символ, не входящий в таблицу текущего режима,
    # закрываем сегмент и начинаем новый.
    
    if not data:
        return version, bit_stream

    current_mode = _choose_segment_mode(data[0])
    segment_start = 0
    
    for i, char in enumerate(data):
        potential_mode = _choose_segment_mode(char)
        if potential_mode != current_mode:
            # Режим сменился, фиксируем предыдущий сегмент
            segment_text = data[segment_start:i]
            segments.append((current_mode, segment_text))
            current_mode = potential_mode
            segment_start = i
            
    # Фиксируем последний сегмент
    segments.append((current_mode, data[segment_start:]))
    
    # --- Сборка битового потока ---
    for mode, segment_text in segments:
        bit_stream += _get_mode_indicator(mode)
        
        char_count = len(segment_text)
        count_len = _get_char_count_indicator_length(version, mode)
        bit_stream += f"{char_count:0{count_len}b}"
        
        if mode == 'numeric':
            bit_stream += encode_numeric(segment_text)
        elif mode == 'alphanumeric':
            bit_stream += encode_alphanumeric(segment_text)
        elif mode == 'byte':
            _, segment_bits = encode_byte(segment_text)
            bit_stream += segment_bits
        # Kanji можно добавить позже по аналогии
            
    # --- Terminator (4 нуля) ---
    bit_stream += '0000'
    
    # --- Дополнение до кратности 8 ---
    while len(bit_stream) % 8 != 0:
        bit_stream += '0'
        
    # --- Байты заполнения (Padding Bytes) ---
    # Преобразуем битовую строку в байты
    data_bytes = bytearray(int(bit_stream[i:i+8], 2) for i in range(0, len(bit_stream), 8))
    
    capacity_bytes = MAX_DATA_CAPACITY_BYTES[level][version]
    
    # Если данных меньше, чем емкость версии, заполняем байтами 0xEC и 0x11
    if len(data_bytes) < capacity_bytes:
        padding_bytes = [0xEC, 0x11]
        idx = 0
        while len(data_bytes) < capacity_bytes:
            data_bytes.append(padding_bytes[idx % 2])
            idx += 1
            
    # Формируем финальную битовую строку из заполненных байтов
    final_bit_stream = ''.join(f"{byte:08b}" for byte in data_bytes)
    
    return version, final_bit_stream