"""
Visual tokens of the app: the portfolio look of Data-Generator (ui/theme.py there), white page, teal and copper.

The colours live in src/shop_warehouse/theme.py, shared with the README charts; this module adds the Mantine theme.
"""
from shop_warehouse.theme import (  # noqa: F401  (re-exported for the app)
    ACCENT,
    COPPER,
    INK,
    PRIMARY,
    SANS_STACK,
    TEAL,
)

MANTINE_THEME = {
    "fontFamily": SANS_STACK,
    "fontFamilyMonospace": "ui-monospace, 'Cascadia Mono', Consolas, monospace",
    "headings": {"fontFamily": SANS_STACK, "fontWeight": "700"},
    "primaryColor": "petrol",
    "primaryShade": 7,
    "colors": {"petrol": TEAL, "copper": COPPER},
    "black": INK,
    "defaultRadius": "sm",
    "fontSizes": {"xs": "12px", "sm": "14px", "md": "15px", "lg": "17px", "xl": "20px"},
}
