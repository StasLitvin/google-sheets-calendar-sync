"""
Google Sheets API возвращает цвет в формате:
  {"red": 0.9, "green": 0.5, "blue": 0.1}
  значения от 0.0 до 1.0

Здесь конвертируем в hex.
"""

def gsheets_color_to_hex(color_dict: dict | None) -> str | None:
    """
    Конвертирует объект Color из Google Sheets API в #RRGGBB.

    Если цвет белый (фон по умолчанию) или отсутствует — возвращает None.
    """
    if not color_dict:
        return None

    r = color_dict.get("red", 0.0)
    g = color_dict.get("green", 0.0)
    b = color_dict.get("blue", 0.0)

    if r >= 0.99 and g >= 0.99 and b >= 0.99:
        return None

    if r == 0.0 and g == 0.0 and b == 0.0 and len(color_dict) == 0:
        return None

    ri = min(int(r * 255), 255)
    gi = min(int(g * 255), 255)
    bi = min(int(b * 255), 255)

    return f"#{ri:02X}{gi:02X}{bi:02X}"
