PRODUCTS = [
    {"code": "product_1", "title": "Мяу от Матрёшек (Крисс)"},
    {"code": "product_2", "title": "СК крисс от Матрёшек ( КРБ-елый/КРС-иний )"},
    {"code": "product_3", "title": "Мёд/Метадон от Матрёшек"},
    {"code": "product_4", "title": "Гаш натур LaMouse"},
    {"code": "product_5", "title": "Гаш натур DryShift"},
    {"code": "product_6", "title": "ШИШ натур Skunk/Amnesia"},
    {"code": "product_7", "title": "ТВ ШОК"},
]

_PRODUCTS_BY_CODE = {product["code"]: product for product in PRODUCTS}


def get_product_title(code: str | None) -> str:
    """Вернуть название товара по его коду или подходящий плейсхолдер."""
    if not code:
        return "Товар не указан"
    product = _PRODUCTS_BY_CODE.get(code)
    return product["title"] if product else "Товар не указан"
