# core/matrix_builder.py

from typing import List, Tuple, Literal
import math
from resources.version_tables import EC_INFO

Level = Literal["L", "M", "Q", "H"]


def _get_matrix_size(version: int) -> int:
    """Возвращает размер холста QR-кода (количество модулей по стороне)."""
    # Размер = 21 + (version - 1) * 4
    return 21 + (version - 1) * 4


def _get_alignment_pattern_positions(version: int) -> List[int]:
    """Возвращает координаты выравнивающих узоров (Alignment Patterns)."""
    # Для версий 1-6 выравнивающих узоров нет
    if version <= 6:
        return []

    # Координаты из спецификации (Таблица 9)
    # Верхняя строка — номер версии, столбцы — координаты (отсчёт от 0)
    # Координаты симметричны относительно центра, поэтому берем только верхнюю половину
    # и зеркально отражаем их
    positions = []
    if version <= 7:
        positions = [6]
    elif version <= 13:
        positions = [6, 18]
    elif version <= 14:
        positions = [6, 22]
    elif version <= 20:
        positions = [6, 26]
    elif version <= 26:
        positions = [6, 30]
    elif version <= 32:
        positions = [6, 22, 38]
    elif version <= 34:
        positions = [6, 24, 44]
    elif version <= 38:
        positions = [6, 26, 46]
    elif version <= 40:
        positions = [6, 30, 58]

    # Добавляем симметричные координаты
    size = _get_matrix_size(version)
    for pos in positions[:]:
        # Отражаем от центра
        positions.append(size - 1 - pos)

    # Исключаем координаты, которые совпадают с поисковыми узорами (0, 6, size-7)
    positions = [p for p in positions if p not in [0, 6, size - 7]]

    # Сортируем для удобства
    return sorted(positions)


def _create_empty_matrix(version: int) -> List[List[int]]:
    """Создает пустую матрицу с рамкой из белых модулей (4 модуля)."""
    size = _get_matrix_size(version)
    # 0 — белый модуль, 1 — черный
    matrix = [[0] * size for _ in range(size)]

    # Добавляем рамку (4 модуля)
    for i in range(4):
        for j in range(size):
            matrix[i][j] = 0
            matrix[size - 1 - i][j] = 0
            matrix[j][i] = 0
            matrix[j][size - 1 - i] = 0

    return matrix


def _draw_finder_pattern(matrix: List[List[int]], x: int, y: int) -> None:
    """Рисует поисковый узор (Finder Pattern) 9x9 с разделителем 1x9."""
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
    """Рисует выравнивающий узор (Alignment Pattern) 5x5."""
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
    """Рисует тайминговые линии (Timing Patterns) по диагонали от поисковых узоров."""
    # Горизонтальная линия (строка 6)
    for x in range(8, size - 8):
        matrix[6][x] = x % 2

    # Вертикальная линия (столбец 6)
    for y in range(8, size - 8):
        matrix[y][6] = y % 2


def _interleave_blocks(data: List[int], ec: List[int], version: int, level: Level) -> List[int]:
    """Переплетает блоки данных и коррекции зигзагообразно.

    Алгоритм: берем по одному байту из каждого блока данных, затем из каждого блока коррекции.
    """
    # Получаем структуру блоков из таблицы EC_INFO
    num_data_blocks, data_block_size, extra_data_blocks, _, ec_block_size = EC_INFO[(version, level)]

    # Разделяем данные на блоки
    data_blocks = []
    for i in range(num_data_blocks):
        # Обычные блоки
        block_size = data_block_size
        # Последние блоки могут быть длиннее на 1 байт
        if i >= num_data_blocks - extra_data_blocks:
            block_size += 1
        data_blocks.append(data[i * block_size : (i + 1) * block_size])

    # Разделяем коррекцию на блоки
    ec_blocks = []
    for i in range(num_data_blocks):
        ec_blocks.append(ec[i * ec_block_size : (i + 1) * ec_block_size])

    # Переплетение
    interleaved = []
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


def _write_data_to_matrix(matrix: List[List[int]], data: List[int], size: int) -> None:
    """Записывает данные в матрицу зигзагообразно."""
    # Направление: 0 — вверх, 1 — вниз
    direction = 0
    # Стартуем с правого верхнего угла (исключая поисковые узоры)
    x = size - 1
    y = size - 1

    # Пропускаем служебные области
    if size >= 23:
        # Выравнивающие узоры в правом верхнем углу
        x -= 2
    if size >= 15:
        # Тайминговая линия
        y -= 2

    # Битовый индекс в данных
    bit_index = 0

    # Идем зигзагом
    while x >= 0:
        # Пропускаем служебные области
        if (x < 9 or x > size - 8) and (y < 9 or y > size - 8):
            # Внутри поискового узора
            pass
        elif x == 6:
            # Внутри тайминговой линии
            pass
        else:
            # Записываем бит
            if data[bit_index // 8] & (1 << (7 - (bit_index % 8))):
                matrix[y][x] = 1
            bit_index += 1

        # Двигаемся
        if direction == 0:
            y -= 1
            if y < 0:
                # Смена направления
                direction = 1
                y = 0
                x -= 2
        else:
            y += 1
            if y >= size:
                # Смена направления
                direction = 0
                y = size - 1
                x -= 2

        # Проверка на выход за пределы
        if x < 0:
            break


def build_qr_matrix(data: List[int], ec: List[int], version: int, level: Level) -> List[List[int]]:
    """Собирает полную матрицу QR-кода."""
    size = _get_matrix_size(version)

    # 1. Создаем холст
    matrix = _create_empty_matrix(version)

    # 2. Рисуем поисковые узоры и разделители
    _draw_finder_pattern(matrix, 0, 0)
    _draw_finder_pattern(matrix, size - 7, 0)
    _draw_finder_pattern(matrix, 0, size - 7)

    # 3. Рисуем тайминговые линии
    _draw_timing_pattern(matrix, size)

    # 4. Рисуем выравнивающие узоры
    for pos in _get_alignment_pattern_positions(version):
        # Верхняя половина
        _draw_alignment_pattern(matrix, pos, 6)
        # Левая половина
        _draw_alignment_pattern(matrix, 6, pos)
        # Нижняя и правая половины (симметрия)
        _draw_alignment_pattern(matrix, size - 7 - pos, pos)
        _draw_alignment_pattern(matrix, pos, size - 7 - pos)

    # 5. Переплетаем данные и коррекцию
    interleaved = _interleave_blocks(data, ec, version, level)

    # 6. Записываем данные в матрицу
    _write_data_to_matrix(matrix, interleaved, size)

    return matrix