"""Resolve product categories from the maintained model catalog."""

import json
import re


def category_is_blank(value):
    return value is None or str(value).strip().lower() in ('', 'nan', 'null', 'none')


def _model_key(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def _series_key(value):
    return value.replace('系列', '').replace('series', '')


class ProductCategoryResolver:
    def __init__(self, catalog):
        self.exact = {}
        self.series = {}
        for category, models in (catalog.items() if isinstance(catalog, dict) else []):
            if category_is_blank(category) or not isinstance(models, list):
                continue
            for model in models:
                key = _model_key(model)
                if key:
                    self.exact.setdefault(key, set()).add(str(category).strip())
                    self.series.setdefault(_series_key(key), set()).add(str(category).strip())

    def resolve(self, products, existing=None):
        if not category_is_blank(existing):
            return existing
        if isinstance(products, str):
            text = products.strip()
            if text.startswith('['):
                try:
                    products = json.loads(text)
                except ValueError:
                    pass
        if not isinstance(products, (list, tuple, set)):
            products = re.split(r'[,，\n]+', str(products or ''))
        categories = set()
        for product in products:
            key = _model_key(product)
            if key:
                categories.update(self.exact.get(key) or self.series.get(_series_key(key)) or ())
        return ','.join(sorted(categories))
