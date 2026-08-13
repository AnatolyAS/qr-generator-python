# core/masking.py

from typing import List, Tuple

# 8 стандартных шаблонов масок (Mask Patterns)
# Функция принимает координаты (i, j) и возвращает True, если модуль нужно инвертировать.
MASK_PATTERNS = [
    lambda i, j: (i + j) % 2 == 0,  # 000: Чередование по сумме координат
    lambda i, j: i % 2 == 0,        # 001: Чередование по строкам
    lambda i, j: j % 3 == 0,        # 010: Чередование по столбцам (шаг 3)
    lambda i, j: (i + j) % 3 == 0,  # 011: Чередование по сумме (шаг 3)
    lambda i, j: ((i // 2) + (j // 3)) % 2 == 0,  # 100: Блоки 2x3
    lambda i, j: ((i * j) % 2) + ((i * j) % 3) == 0, # 101: Произведение
    lambda i, j: (((i * j) % 2) + ((i * j) % 3)) % 2 == 0, # 110: Произведение (XOR 2)
    lambda i, j: (((i + j) % 2) + ((i * j) % 3)) % 2 == 0  # 111: Комбинированная
]


def _apply_mask(matrix: List[List[int]], mask_idx: int) -> List[List[int]]:
    """Применяет маску к матрице данных (инвертирует биты согласно шаблону)."""
    size = len(matrix)
    pattern = MASK_PATTERNS[mask_idx]
    
    masked_matrix = [row[:] for row in matrix]  # Создаем копию
    
    for i in range(size):
        for j in range(size):
            # Применяем маску только к области данных (не трогаем служебные узоры)
            # Поисковые узоры и разделители всегда находятся по краям (0-8) или в углах.
            # Мы будем учитывать это при финальной отрисовке в matrix_builder.py.
            # Здесь для упрощения оценки инвертируем всё, а при отрисовке наложим "замазку".
            if pattern(i, j):
                masked_matrix[i][j] ^= 1
    return masked_matrix


def _calculate_penalty_1(matrix: List[List[int]]) -> int:
    """Rule 1: Пять и более одноцветных модулей в ряд (горизонтально или вертикально)."""
    penalty = 0
    size = len(matrix)
    
    # Горизонтальные линии
    for row in matrix:
        current_color = row[0]
        count = 1
        for i in range(1, size):
            if row[i] == current_color:
                count += 1
            else:
                if count >= 5:
                    penalty += 3 + (count - 5)
                current_color = row[i]
                count = 1
        if count >= 5:
            penalty += 3 + (count - 5)
            
    # Вертикальные линии
    for col in range(size):
        current_color = matrix[0][col]
        count = 1
        for i in range(1, size):
            if matrix[i][col] == current_color:
                count += 1
            else:
                if count >= 5:
                    penalty += 3 + (count - 5)
                current_color = matrix[i][col]
                count = 1
        if count >= 5:
            penalty += 3 + (count - 5)
            
    return penalty


def _calculate_penalty_2(matrix: List[List[int]]) -> int:
    """Rule 2: Блоки 2x2 одного цвета."""
    penalty = 0
    size = len(matrix) - 1
    
    for i in range(size):
        for j in range(size):
            color = matrix[i][j]
            if (matrix[i+1][j] == color and
                matrix[i][j+1] == color and
                matrix[i+1][j+1] == color):
                penalty += 3
    return penalty


def _calculate_penalty_3(matrix: List[List[int]]) -> int:
    """Rule 3: Шаблоны 1011101 (7 модулей) и их вариации.
    Проверяет наличие 11 черных, 3 белых, 1 черного, 3 белых, 1 черного (1011101000... или ...0001011101)."""
    penalty = 0
    size = len(matrix)
    pattern1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    pattern2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    
    # Горизонтально
    for row in matrix:
        row_str = ''.join(map(str, row))
        if '10111010000' in row_str or '00001011101' in row_str:
            penalty += 40
            
    # Вертикально
    for col in range(size):
        col_str = ''.join(str(matrix[i][col]) for i in range(size))
        if '10111010000' in col_str or '00001011101' in col_str:
            penalty += 40
            
    return penalty


def _calculate_penalty_4(matrix: List[List[int]]) -> int:
    """Rule 4: Пропорция темных и светлых модулей.
    Штраф, если темных модулей не ~50%."""
    penalty = 0
    size = len(matrix)
    dark_modules = sum(sum(row) for row in matrix)
    total_modules = size * size
    percent = (dark_modules * 100) / total_modules
    
    # Округляем до ближайшего кратного 5
    remainder = percent % 5
    if remainder < 2.5:
        rounded = percent - remainder
    else:
        rounded = percent + (5 - remainder)
        
    diff = abs(50 - rounded)
    penalty += (diff // 5) * 10
    
    return penalty


def calculate_total_penalty(matrix: List[List[int]]) -> int:
    """Суммирует все штрафы для одной маски."""
    return (
        _calculate_penalty_1(matrix) +
        _calculate_penalty_2(matrix) +
        _calculate_penalty_3(matrix) +
        _calculate_penalty_4(matrix)
    )


def apply_best_mask(data_matrix: List[List[int]]) -> Tuple[List[List[int]], int]:
    """
    Применяет все 8 масок, оценивает их по штрафам и возвращает лучшую.
    
    Returns:
        tuple: (матрица_с_лучшей_маской, номер_маски_от_0_до_7)
    """
    best_penalty = float('inf')
    best_matrix = []
    best_mask_idx = 0
    
    for mask_idx in range(8):
        # Важно: применяем маску к копии данных
        masked = _apply_mask(data_matrix, mask_idx)
        penalty = calculate_total_penalty(masked)
        
        if penalty < best_penalty:
            best_penalty = penalty
            best_matrix = masked
            best_mask_idx = mask_idx
            
    return best_matrix, best_mask_idx