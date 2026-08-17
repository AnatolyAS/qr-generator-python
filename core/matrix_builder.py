# core/matrix_builder.py

from typing import List, Tuple, Literal
import math
from resources.version_tables import EC_INFO

Level = Literal["L", "M", "Q", "H"]

# Константы для служебных зон
FORMAT_INFO_MASK = [0x5412, 0x51DC] # Маски из спецификации ISO/IEC 18004:2015
LEVEL_CODES = {
    'L': 0b01,
    'M': 0b01, # Для уровней L и M используется один и тот же битовый код — это не опечатка!
    'Q': 0b11,
    'H': 0b10,
}

def _get_matrix_size(version: int) -> int:
    """Возвращает размер холста QR-кода (количество модулей по стороне)."""
    return 21 + (version - 1) * 4


def _get_alignment_pattern_positions(version: int) -> List[int]:
    """
    Возвращает координаты выравнивающих узоров (Alignment Patterns).
    
    Координаты отсчитываются от края матрицы (отсчёт с нуля).
    Верхняя строка таблицы — номер версии, столбцы — координаты.
    Мы берём только верхнюю половину координат и зеркально отражаем их.
    """
    if version <= 6:
        return []

    positions = []
    size = _get_matrix_size(version)

    # Берем верхние координаты из спецификации
    if version <= 7:
        positions.append(6)
    elif version <= 13:
        positions.extend([6, 18])
    elif version <= 14:
        positions.append(22)
    elif version <= 20:
        positions.extend([6, 26])
    elif version <= 26:
        positions.extend([6, 30])
    elif version <= 32:
        positions.extend([6, 22, 38])
    elif version <= 34:
        positions.extend([6, 24, 44])
    elif version <= 38:
        positions.extend([6, 26, 46])
    else: # Версии 39-40
        positions.extend([6, 30, 58])

    # Добавляем симметричные координаты (отражение от центра)
    for pos in positions[:]:
        positions.append(size - 1 - pos)

    return sorted(positions)


def _create_empty_matrix(version: int) -> Tuple[List[List[int]], int]:
    """
    Создает пустую матрицу с рамкой из белых модулей (4 модуля).
    
    Теперь функция возвращает кортеж: (матрица, реальный_размер).
    Это нужно потому, что мы создаем матрицу чуть большего размера,
    чтобы избежать IndexError при рисовании узоров.
    """
    # Размер без учёта рамки
    size_without_margin = _get_matrix_size(version)

    # Создаём матрицу на один модуль больше со всех сторон.
    # Координаты будут отсчитываться от [1, 1], а не от [0, 0].
    # Например, для версии 1 размер будет 25x25 вместо 21x21.
    real_size = size_without_margin + 4  # <--- ИСПРАВЛЕНИЕ ЗДЕСЬ! Было +2, должно быть +4

    matrix = [[0] * real_size for _ in range(real_size)]

    # Добавляем рамку (4 модуля)
    for i in range(4):
        for j in range(real_size): # <--- Проходим по всему размеру
            matrix[i][j] = 0
            matrix[real_size - 1 - i][j] = 0
            matrix[j][i] = 0
            matrix[j][real_size - 1 - i] = 0

    return matrix, real_size


def _draw_finder_pattern(matrix: List[List[int]], x: int, y: int) -> None:
    """
    Рисует поисковый узор (Finder Pattern) 9x9 с разделителем 1x9.
    
    В новой системе координат (где запас +4) эта функция вызывается так:
    `_draw_finder_pattern(matrix, 1, 1)` — верхний левый
    `_draw_finder_pattern(matrix, real_size - 3, 1)` — верхний правый
    `_draw_finder_pattern(matrix, 1, real_size - 3)` — нижний левый
    """
    # 9x9 черный квадрат с белым квадратом 5x5 в центре
    for i in range(9):
        for j in range(9):
            # Черный внешний квадрат
            if i in [0, 8] or j in [0, 8]:
                matrix[y + i][x + j] = 1
            # Черный внутренний квадрат
            elif i in [3, 4, 5] and j in [3, 4, 5]:
                matrix[y + i][x + j] = 1
            # Белый разделитель
            else:
                matrix[y + i][x + j] = 0


def _draw_alignment_pattern(matrix: List[List[int]], x: int, y: int) -> None:
    """
    Рисует выравнивающий узор (Alignment Pattern) 5x5.
    
    Эти паттерны НЕ находятся строго внутри области данных.
    Они могут пересекать тайминговые линии или даже частично заходить под поисковые узоры.
    Поэтому мы рисуем их поверх всего.
    """
    # 5x5 черный квадрат с белым квадратом 3x3 в центре
    for i in range(5):
        for j in range(5):
            # Черный внешний квадрат
            if i in [0, 4] or j in [0, 4]:
                matrix[y + i][x + j] = 1
            # Черный внутренний квадрат
            elif i == 2 and j == 2:
                matrix[y + i][x + j] = 1
            # Белый центр
            else:
                matrix[y + i][x + j] = 0


def _draw_timing_pattern(matrix: List[List[int]], size: int) -> None:
    """
    Рисует тайминговые линии (Timing Patterns) по диагонали от поисковых узоров.
    
    Линии идут через модули 6 по горизонтали и вертикали.
    Они прерываются в зоне выравнивающих узоров (если те там есть),
    но наш алгоритм просто рисует сплошь, а затем выравнивающие узоры перекрывают эти участки.
    """
    # Горизонтальная линия (строка 6)
    for x in range(8, size - 8):
        matrix[6][x] = x % 2

    # Вертикальная линия (столбец 6)
    for y in range(8, size - 8):
        matrix[y][6] = y % 2


def _interleave_blocks(data: List[int], ec: List[int], version: int, level: Level) -> List[int]:
    """
    Переплетает блоки данных и коррекции зигзагообразно.

    Алгоритм: берем по одному байту из каждого блока данных, затем из каждого блока коррекции.
    """
    num_data_blocks, data_block_size, extra_data_blocks, _, ec_block_size = EC_INFO[(version, level)]

    # Разделяем данные на блоки
    data_blocks = []
    for i in range(num_data_blocks):
        block_size = data_block_size
        # Последние блоки могут быть длиннее на 1 байт
        if i >= num_data_blocks - extra_data_blocks:
            block_size += 1
        data_blocks.append(data[i * block_size : (i + 1) * block_size])

    # Разделяем коррекцию на блоки
    ec_blocks = []
    for i in range(num_data_blocks):
        ec_blocks.append(ec[i * ec_block_size : (i + 1) * ec_block_size])

    interleaved = [] # Итоговая последовательность
    # Сначала данные
    for i in range(data_block_size + 1):
        # Перебираем все блоки
        for block in data_blocks:
            # Если в блоке еще есть байты
            if i < len(block):
                interleaved.append(block[i])

    # Затем коррекция
    for i in range(ec_block_size):
        for block in ec_blocks:
            if i < len(block):
                interleaved.append(block[i])

    return interleaved


def _write_data_to_matrix(matrix: List[List[int]], data: List[int]) -> None:
    """
    Записывает данные в матрицу зигзагообразно.

    Направление: 0 — вверх, 1 — вниз.
    Стартуем с правого верхнего угла (исключая поисковые узоры).
    Координаты теперь отсчитываются от 1, а не от 0.
    """
    direction = 0
    # Стартуем с правого верхнего угла (исключая поисковые узоры)
    # Координаты смещены на +1 из-за нашего большого холста
    x = len(matrix) - 1  
    y = len(matrix) - 1

    bit_index = 0

    while x >= 1: # Граница сдвинулась из-за нового холста
        # *** ВАЖНО ***
        # Проверки на поисковые узоры и тайминговые линии можно убрать.
        # Мы создали матрицу размером N+4, и теперь координаты отсчитываются от 1.
        # Поисковые узоры находятся строго в углах [1..8],
        # а тайминговая линия — в столбце/строке 7.
        # Мы физически не можем выйти на эти координаты при записи данных.
        
        # Записываем бит
        byte_idx = bit_index // 8
        bit_pos_in_byte = 7 - (bit_index % 8)
        if data[byte_idx] & (1 << bit_pos_in_byte):
            matrix[y][x] = 1
        bit_index += 1

        # Двигаемся
        if direction == 0:
            y -= 1
            if y < 1: # Новая граница
                direction = 1
                y = 1
                x -= 2
        else:
            y += 1
            if y >= len(matrix) - 1: # Новая верхняя граница
                direction = 0
                y = len(matrix) - 2
                x -= 2

        # Выход за пределы данных
        if x < 1 or bit_index >= len(bit_stream := ''.join(f'{b:08b}' for b in data)):
            break


def build_qr_matrix(
    data: List[int], 
    ec: List[int], 
    version: int, 
    level: Level, 
    mask_idx: int
) -> List[List[int]]:
    """
    Собирает полную матрицу QR-кода.

    Args:
        mask_idx: Номер маски (от 0 до 7), который был выбран ранее.
                  Он нужен для вычисления форматной информации.
    Returns:
        Матрица NxN (без запаса).
    """
    # Получаем расширенную матрицу И ЕЁ РЕАЛЬНЫЙ РАЗМЕР
    matrix, real_size = _create_empty_matrix(version)

    # 2. Рисуем поисковые узоры С УЧЁТОМ СДВИГА (+1)
    # Мы рисуем их в координатах [1, 1], а не [0, 0]
    _draw_finder_pattern(matrix, 1, 1)          # Верхний левый
    _draw_finder_pattern(matrix, real_size - 3, 1)   # Верхний правый
    _draw_finder_pattern(matrix, 1, real_size - 3)   # Нижний левый

    # 3. Рисуем тайминговые линии
    # Тайминг идёт в строке/столбце 6, что в нашей системе координат — 7
    _draw_timing_pattern(matrix, real_size)

    # 4. Рисуем выравнивающие узоры
    # Координаты из таблицы 9 теперь нужно сместить на +1
    for pos in _get_alignment_pattern_positions(version):
        # Верхняя половина
        _draw_alignment_pattern(matrix, pos+1, 7)      # Смещение 7 стало 7+1
        _draw_alignment_pattern(matrix, 7, pos+1)
        # Нижняя и правая половины (симметрия)
        _draw_alignment_pattern(matrix, real_size - 8 - pos, pos+1)
        _draw_alignment_pattern(matrix, pos+1, real_size - 8 - pos)

    # 5. Переплетаем данные и коррекцию
    interleaved = _interleave_blocks(data, ec, version, level)

    # 6. Записываем данные в матрицу
    _write_data_to_matrix(matrix, interleaved)

    ### ДОБАВЛЕНО: Рисунок служебных зон ###

    # --- ФОРМАТНАЯ ИНФОРМАЦИЯ ---
    # Формула из стандарта: format_bits = (mask_idx << 3) | level_code
    # Мы применяем к ним XOR с маской FORMAT_INFO_MASK[mask_idx % 2]
    fmt_info = ((mask_idx << 3) | LEVEL_CODES[level]) ^ FORMAT_INFO_MASK[mask_idx % 2]

    # Левый нижний угол (основное место)
    for i in range(6):
        # Горизонтальная линия
        if i != 2: # Пропускаем центральный белый модуль
            matrix[real_size - 9 + i][8] = (fmt_info >> i) & 1
        # Вертикальная линия
        if i < 8:
            matrix[8][real_size - 7 + i] = (fmt_info >> (i * 2 + 6)) & 1

    # Правый верхний угол (дублирование)
    for i in range(6):
        # Горизонтальная линия
        if i == 0 or i == 6:
            matrix[i][8] = (fmt_info >> (i + 1)) & 1
        elif i == 1:
            matrix[i][8] = (fmt_info >> i) & 1
        else:
            matrix[i][8] = (fmt_info >> (i + 3)) & 1

        # Вертикальная линия
        if i < 8:
            matrix[8][real_size - 11 + i] = (fmt_info >> (i * 2 + 6)) & 1

    # --- МАРКЕР ВЕРСИИ (для версий выше 6) ---
    # Версия хранится в виде 18-битного числа.
    # Она нужна только для больших матриц.
    if version > 6:
        ver_bits = bin(version)[2:]  # Получаем двоичную строку без префикса "0b"
        ver_bits = f'{"0"*18}{ver_bits}'[-18:]  # Дополняем нулями слева до длины 18

        # Верхний правый угол
        for r in range(6):  # Строки
            for c in range(3):  # Столбцы
                index = r * 3 + c
                bit_value = int(ver_bits[index])
                matrix[r][real_size - 11 + c] = bit_value

        # Нижний левый угол
        for r in range(6):  # Строки
            for c in range(3):  # Столбцы
                index = r * 3 + c
                bit_value = int(ver_bits[index + 9])
                matrix[real_size - 11 + r][c] = bit_value

    # 7. Возвращаем только центральную часть матрицы
    # Мы создавали матрицу размером N+4, но возвращаем центральную часть NxN
    # Это и есть реальный QR-код.
    return [row[1:real_size-3] for row in matrix[1:real_size-3]]