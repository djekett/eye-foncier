"""Tags personnalisés — parcelles."""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Accès dict dans un template : {{ mydict|get_item:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, "")
    return ""


@register.filter
def format_fcfa(value):
    """Formate un nombre en FCFA : 15000 → '15 000'"""
    try:
        return "{:,.0f}".format(float(value)).replace(",", " ")
    except (ValueError, TypeError):
        return value
