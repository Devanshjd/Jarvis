"""
J.A.R.V.I.S — Theme System
Clean, modern dark theme with glow accents.
"""

COLORS = {
    # Backgrounds — deep dark with subtle blue tint
    "bg":          "#0a0e17",
    "bg2":         "#0f1520",
    "bg3":         "#141c2b",
    "card":        "#111827",
    "card_hover":  "#1a2332",

    # Primary — cyan/blue glow
    "primary":     "#00d4ff",
    "primary_dim": "#0099bb",
    "primary_glow":"#0a2a3a",

    # Accents
    "accent":      "#ff6b35",
    "gold":        "#fbbf24",
    "green":       "#10b981",
    "red":         "#ef4444",
    "purple":      "#8b5cf6",

    # Text
    "text":        "#e2e8f0",
    "text_dim":    "#64748b",
    "text_muted":  "#334155",

    # Borders
    "border":      "#1e293b",
    "border_glow": "#0a3040",

    # Special
    "user_msg":    "#ffd8b0",
    "jar_msg":     "#e2e8f0",
    "white":       "#ffffff",
}

FONTS = {
    "mono":       ("Consolas", 10),
    "mono_sm":    ("Consolas", 9),
    "mono_xs":    ("Consolas", 8),
    "title":      ("Segoe UI", 22, "bold"),
    "title_md":   ("Segoe UI", 16, "bold"),
    "title_sm":   ("Segoe UI", 13, "bold"),
    "heading":    ("Segoe UI Semibold", 11),
    "label":      ("Segoe UI", 8),
    "label_md":   ("Segoe UI", 9),
    "msg":        ("Segoe UI", 11),
    "msg_sm":     ("Segoe UI", 10),
    "msg_xs":     ("Segoe UI", 9),
    "clock":      ("Consolas", 12),
    "stat":       ("Consolas", 14, "bold"),
    "stat_sm":    ("Consolas", 11, "bold"),
    "btn":        ("Segoe UI Semibold", 9),
    "btn_lg":     ("Segoe UI Semibold", 10),
}

STATUS_ITEMS = [
    ("STARK INDUSTRIES", "text_dim"),
    ("ALL SYSTEMS NOMINAL", "green"),
    ("v5.0", "text_dim"),
]
