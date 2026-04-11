"""
J.A.R.V.I.S — Theme System
Clean, modern dark theme with glow accents.
"""

COLORS = {
    # Shell
    "bg":          "#05070b",
    "shell":       "#090c11",
    "bg2":         "#0b0f14",
    "bg3":         "#10161d",
    "panel":       "#0d131a",
    "panel_alt":   "#111924",
    "card":        "#0f151d",
    "card_hover":  "#16202c",

    # Primary glow
    "primary":     "#49dcff",
    "primary_dim": "#1da8c5",
    "primary_glow":"#123845",

    # Accents
    "accent":      "#52e3b1",
    "gold":        "#f5c768",
    "green":       "#34d399",
    "red":         "#fb7185",
    "purple":      "#7c8cff",

    # Text
    "text":        "#edf3fb",
    "text_dim":    "#93a3b8",
    "text_muted":  "#5d6a7a",

    # Borders / lines
    "border":      "#202a36",
    "border_soft": "#141b24",
    "border_glow": "#153746",

    # Special
    "user_msg":    "#d7ecff",
    "jar_msg":     "#edf3fb",
    "white":       "#ffffff",
}

FONTS = {
    "mono":       ("Cascadia Code", 10),
    "mono_sm":    ("Cascadia Code", 9),
    "mono_xs":    ("Cascadia Code", 8),
    "title":      ("Segoe UI Semibold", 21),
    "title_md":   ("Segoe UI Semibold", 15),
    "title_sm":   ("Segoe UI Semibold", 12),
    "heading":    ("Segoe UI Semibold", 10),
    "label":      ("Segoe UI", 8),
    "label_md":   ("Segoe UI", 9),
    "msg":        ("Segoe UI", 11),
    "msg_sm":     ("Segoe UI", 10),
    "msg_xs":     ("Segoe UI", 9),
    "clock":      ("Cascadia Code", 11),
    "stat":       ("Cascadia Code", 14, "bold"),
    "stat_sm":    ("Cascadia Code", 11, "bold"),
    "btn":        ("Segoe UI Semibold", 9),
    "btn_lg":     ("Segoe UI Semibold", 10),
}

STATUS_ITEMS = [
    ("STARK INDUSTRIES", "text_dim"),
    ("ALL SYSTEMS NOMINAL", "green"),
    ("v5.0", "text_dim"),
]
