"""
JARVIS — Autonomous Assignment Diagram Generator
Generates all 3 required network diagrams for the Safe House assignment:
  1. Physical LAN diagram (floor plan with devices and cabling)
  2. Logical LAN diagram (3-tier hierarchy with VLANs)
  3. Logical WAN diagram (DWDM optical grid topology)
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D
import numpy as np
import os

OUT = os.path.dirname(os.path.abspath(__file__))

# ─── Colour palette ──────────────────────────────────────────────────────────
C_ROOM       = "#EAF4FB"
C_ROOM_COMMS = "#FFF176"   # yellow highlight Room 8
C_ROOM_PANIC = "#FFCCBC"   # orange tint Room 5
C_BORDER     = "#37474F"
C_FIBER      = "#F57F17"   # orange = OS2 SMF backbone
C_CAT6       = "#1565C0"   # blue  = Cat6A
C_WAN_PRI    = "#2E7D32"   # dark green = 100G WDM
C_WAN_ISP    = "#6A1B9A"   # purple = 10G ISP
C_SWITCH     = "#0D47A1"
C_CORE       = "#B71C1C"
C_DIST       = "#1B5E20"
C_ACCESS     = "#0D47A1"
C_FW         = "#E65100"
C_ROUTER     = "#4A148C"
C_CCTV       = "#880E4F"
C_ROADM      = "#004D40"


def draw_device(ax, cx, cy, w, h, label, color, fontsize=7, textcolor="white", sublabel=""):
    box = FancyBboxPatch((cx - w/2, cy - h/2), w, h,
                         boxstyle="round,pad=0.02",
                         facecolor=color, edgecolor="white", linewidth=1.2, zorder=5)
    ax.add_patch(box)
    ax.text(cx, cy + (0.07 if sublabel else 0), label,
            ha="center", va="center", fontsize=fontsize, color=textcolor,
            fontweight="bold", zorder=6, wrap=True)
    if sublabel:
        ax.text(cx, cy - 0.1, sublabel, ha="center", va="center",
                fontsize=fontsize - 1, color=textcolor, zorder=6)


def arrow(ax, x1, y1, x2, y2, color, lw=1.5, style="-", zorder=3):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                linestyle=style, connectionstyle="arc3,rad=0"),
                zorder=zorder)


def line(ax, x1, y1, x2, y2, color, lw=2, style="-", zorder=3):
    ax.plot([x1, x2], [y1, y2], color=color, lw=lw, linestyle=style, zorder=zorder)


# ═══════════════════════════════════════════════════════════════════════════════
#  DIAGRAM 1 — Physical LAN (Floor Plan)
# ═══════════════════════════════════════════════════════════════════════════════

def diagram_physical_lan():
    fig, ax = plt.subplots(figsize=(20, 15))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("#F5F5F5")
    fig.patch.set_facecolor("#FAFAFA")

    # Title
    ax.text(5, 7.7, "Safe House — Physical LAN Network Diagram",
            ha="center", va="center", fontsize=16, fontweight="bold", color=C_BORDER)
    ax.text(5, 7.45, "30m × 10m Building  |  Hierarchical Network Model  |  OS2 SMF Backbone + Cat6A Access",
            ha="center", va="center", fontsize=9, color="#546E7A")

    # ── Room grid layout (4 rows × 3 cols) ───────────────────────────────────
    # col centres: 1.2, 5.0, 8.8  |  row centres: 1.2, 2.8, 4.4, 6.0
    rooms = {
        # (number, col_cx, row_cy, label_override, bg)
        1:  (1.2, 1.2, "Room 1",  C_ROOM),
        2:  (5.0, 1.2, "Room 2",  C_ROOM),
        3:  (8.8, 1.2, "Room 3",  C_ROOM),
        4:  (8.8, 2.8, "Room 4",  C_ROOM),
        5:  (5.0, 2.8, "Room 5\n(Panic Room)", C_ROOM_PANIC),
        6:  (1.2, 2.8, "Room 6",  C_ROOM),
        7:  (1.2, 4.4, "Room 7",  C_ROOM),
        8:  (5.0, 4.4, "Room 8\nComms (Core)", C_ROOM_COMMS),
        9:  (8.8, 4.4, "Room 9",  C_ROOM),
        10: (8.8, 6.0, "Room 10", C_ROOM),
        11: (5.0, 6.0, "Room 11", C_ROOM),
        12: (1.2, 6.0, "Room 12", C_ROOM),
    }

    RW, RH = 2.8, 1.4   # room width, height

    for rnum, (cx, cy, label, bg) in rooms.items():
        rect = FancyBboxPatch((cx - RW/2, cy - RH/2), RW, RH,
                              boxstyle="round,pad=0.04",
                              facecolor=bg, edgecolor=C_BORDER, linewidth=1.8, zorder=2)
        ax.add_patch(rect)
        ax.text(cx, cy + 0.4, label, ha="center", va="center",
                fontsize=8, color=C_BORDER, fontweight="bold", zorder=3)

    # ── Access switches (one per room, small box) ─────────────────────────────
    def access_sw(ax, cx, cy, label="SW"):
        draw_device(ax, cx, cy, 0.7, 0.25, label, C_ACCESS, fontsize=6)

    for rnum, (cx, cy, *_) in rooms.items():
        if rnum == 8:
            continue   # Room 8 gets full core rack
        sw_y = cy - 0.05
        access_sw(ax, cx, sw_y, f"SW-{rnum:02d}")
        # 4 PCs per room (small dots)
        for i, px in enumerate(np.linspace(cx - 1.1, cx + 1.1, 4)):
            ax.plot(px, cy - 0.45, "s", color="#546E7A", markersize=4, zorder=4)
            line(ax, px, cy - 0.35, cx, sw_y - 0.12, C_CAT6, lw=0.7)

    # ── Room 8 core rack ─────────────────────────────────────────────────────
    r8cx, r8cy = 5.0, 4.4
    draw_device(ax, r8cx - 0.55, r8cy + 0.18, 0.75, 0.22, "CORE-1", C_CORE, fontsize=6)
    draw_device(ax, r8cx + 0.55, r8cy + 0.18, 0.75, 0.22, "CORE-2", C_CORE, fontsize=6)
    draw_device(ax, r8cx,        r8cy - 0.10, 0.80, 0.22, "FW PA-3220", C_FW, fontsize=6)
    draw_device(ax, r8cx,        r8cy - 0.38, 0.90, 0.22, "ASR 1001-X", C_ROUTER, fontsize=6)
    draw_device(ax, r8cx - 0.85, r8cy - 0.10, 0.55, 0.22, "CCTV-A", C_CCTV, fontsize=6)
    draw_device(ax, r8cx + 0.85, r8cy - 0.10, 0.55, 0.22, "CCTV-B", C_CCTV, fontsize=6)
    # Core-Core LAG bond
    line(ax, r8cx - 0.18, r8cy + 0.18, r8cx + 0.18, r8cy + 0.18, "#FF6F00", lw=2.5)
    ax.text(r8cx, r8cy + 0.23, "40GbE LAG", ha="center", fontsize=5, color="#FF6F00", fontweight="bold")

    # ── Distribution switches (3 nodes) ──────────────────────────────────────
    # Dist-A covers Rooms 1-4 → placed near Room 3/4 boundary
    dist = {
        "Dist-A": (8.8, 2.0),   # right side, serves Rooms 1,2,3,4
        "Dist-B": (1.2, 3.6),   # left side, serves Rooms 5,6,7,8
        "Dist-C": (5.0, 5.2),   # top-center, serves Rooms 9,10,11,12
    }
    for dlabel, (dcx, dcy) in dist.items():
        draw_device(ax, dcx, dcy, 1.0, 0.28, dlabel, C_DIST, fontsize=7)

    # ── OS2 Fibre: Core → Distribution ───────────────────────────────────────
    for _, (dcx, dcy) in dist.items():
        # two lines: CORE-1 and CORE-2 each connect to distribution switch
        line(ax, r8cx - 0.55, r8cy + 0.18, dcx, dcy + 0.14, C_FIBER, lw=2.2)
        line(ax, r8cx + 0.55, r8cy + 0.18, dcx, dcy + 0.14, C_FIBER, lw=1.4, style="--")
    ax.text(6.3, 3.6, "OS2 SMF\n10GbaseLR", ha="center", fontsize=6.5,
            color=C_FIBER, fontweight="bold")

    # ── Cat6A: Distribution → Access switches ────────────────────────────────
    dist_assignments = {
        "Dist-A": [3, 4],
        "Dist-B": [6, 7],
        "Dist-C": [11, 12],
    }
    # simplified connections for clarity
    for dlabel, rnums in dist_assignments.items():
        dcx, dcy = dist[dlabel]
        for rnum in rnums:
            rcx, rcy, *_ = rooms[rnum]
            line(ax, dcx, dcy - 0.14, rcx, rcy + 0.15, C_CAT6, lw=1.3)

    # Rooms 1, 2, 9, 10 connect directly to nearest dist
    for rnum, (dcx, dcy) in [("Dist-A", dist["Dist-A"]), ("Dist-C", dist["Dist-C"])]:
        pass
    line(ax, dist["Dist-A"][0], dist["Dist-A"][1] - 0.14,
         rooms[1][0], rooms[1][1] + 0.15, C_CAT6, lw=1.3)
    line(ax, dist["Dist-A"][0], dist["Dist-A"][1] - 0.14,
         rooms[2][0], rooms[2][1] + 0.15, C_CAT6, lw=1.3)
    line(ax, dist["Dist-C"][0], dist["Dist-C"][1] - 0.14,
         rooms[9][0], rooms[9][1] + 0.15, C_CAT6, lw=1.3)
    line(ax, dist["Dist-C"][0], dist["Dist-C"][1] - 0.14,
         rooms[10][0], rooms[10][1] + 0.15, C_CAT6, lw=1.3)
    # Room 5 connects to Dist-B
    line(ax, dist["Dist-B"][0], dist["Dist-B"][1] - 0.14,
         rooms[5][0], rooms[5][1] + 0.15, C_CAT6, lw=1.3)

    # ── WAN external connections from Room 8 ─────────────────────────────────
    ax.annotate("", xy=(5.0, 7.2), xytext=(5.0, 4.95),
                arrowprops=dict(arrowstyle="-|>", color=C_WAN_PRI, lw=2.5))
    ax.text(5.45, 6.5, "100Gbps DWDM\nWDM → London HQ", fontsize=7.5,
            color=C_WAN_PRI, fontweight="bold")

    ax.annotate("", xy=(9.5, 7.2), xytext=(5.55, 4.25),
                arrowprops=dict(arrowstyle="-|>", color=C_WAN_ISP, lw=2.0,
                                connectionstyle="arc3,rad=-0.25"))
    ax.text(8.0, 6.3, "10GBase-LR SFP+\n→ ISP Router", fontsize=7.5,
            color=C_WAN_ISP, fontweight="bold")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_items = [
        Line2D([0], [0], color=C_FIBER, lw=2.5, label="OS2 SMF Backbone (10GbaseLR)"),
        Line2D([0], [0], color=C_FIBER, lw=1.5, ls="--", label="OS2 SMF Redundant Uplink"),
        Line2D([0], [0], color=C_CAT6, lw=2, label="Cat6A UTP (Access / 1GbE)"),
        Line2D([0], [0], color=C_WAN_PRI, lw=2.5, label="100G DWDM WAN to London HQ"),
        Line2D([0], [0], color=C_WAN_ISP, lw=2, label="10GBase-LR SFP+ (ISP)"),
        mpatches.Patch(color=C_CORE, label="Core Switch (Cisco Cat 9500)"),
        mpatches.Patch(color=C_DIST, label="Distribution Switch (Cisco Cat 9300)"),
        mpatches.Patch(color=C_ACCESS, label="Access Switch (Cisco Cat 9200L)"),
        mpatches.Patch(color=C_FW, label="Hardware Firewall (Palo Alto PA-3220)"),
        mpatches.Patch(color=C_ROUTER, label="Border Router (Cisco ASR 1001-X)"),
        mpatches.Patch(color=C_CCTV, label="CCTV Aggregation Switch (independent circuits)"),
        mpatches.Patch(color=C_ROOM_COMMS, label="Comms Room (Room 8) — Core Layer"),
        mpatches.Patch(color=C_ROOM_PANIC, label="Panic Room (Room 5) — Physical Security"),
    ]
    ax.legend(handles=legend_items, loc="lower left", fontsize=6.5,
              framealpha=0.92, edgecolor=C_BORDER, title="Legend", title_fontsize=7.5,
              bbox_to_anchor=(0.0, 0.0))

    out_path = os.path.join(OUT, "diagram1_physical_LAN.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[OK] {out_path}")
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
#  DIAGRAM 2 — Logical LAN (3-tier hierarchy)
# ═══════════════════════════════════════════════════════════════════════════════

def diagram_logical_lan():
    fig, ax = plt.subplots(figsize=(20, 14))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("#F8F9FA")
    fig.patch.set_facecolor("#F8F9FA")

    ax.text(5, 8.25, "Safe House — Logical LAN Network Diagram",
            ha="center", fontsize=16, fontweight="bold", color=C_BORDER)
    ax.text(5, 7.95, "Three-Layer Hierarchical Model  |  VLAN Segmentation  |  Dual-Path Redundancy",
            ha="center", fontsize=9, color="#546E7A")

    # ── Layer bands ───────────────────────────────────────────────────────────
    bands = [
        (0.3, 0.55, "#FCE4EC", "ACCESS LAYER  (Rooms 1–12)"),
        (2.6, 1.05, "#E8F5E9", "DISTRIBUTION LAYER"),
        (4.5, 1.1,  "#E3F2FD", "CORE LAYER"),
        (6.5, 0.85, "#FFF3E0", "BORDER LAYER"),
        (7.6, 0.65, "#EDE7F6", "WAN / EXTERNAL"),
    ]
    for (y0, height, colour, label) in bands:
        rect = patches.FancyBboxPatch((0.1, y0), 9.8, height,
                                       boxstyle="round,pad=0.04",
                                       facecolor=colour, edgecolor="#B0BEC5",
                                       linewidth=1.2, alpha=0.6, zorder=1)
        ax.add_patch(rect)
        ax.text(0.25, y0 + height/2, label, va="center", fontsize=8,
                color=C_BORDER, fontweight="bold", rotation=90 if height < 0.5 else 0)

    # ── Access switches (12, spread across bottom) ────────────────────────────
    acc_xs = np.linspace(0.75, 9.25, 12)
    acc_y = 0.55
    for i, x in enumerate(acc_xs):
        draw_device(ax, x, acc_y, 0.62, 0.28, f"SW-{i+1:02d}\nVLAN 10/40", C_ACCESS, fontsize=5.5)

    # ── Distribution switches (3) ─────────────────────────────────────────────
    dist_xs = [2.2, 5.0, 7.8]
    dist_y = 3.0
    dist_labels = ["Dist-A\n(Rooms 1-4)", "Dist-B\n(Rooms 5-8)", "Dist-C\n(Rooms 9-12)"]
    for dx, dlabel in zip(dist_xs, dist_labels):
        draw_device(ax, dx, dist_y, 1.1, 0.38, dlabel, C_DIST, fontsize=7)

    # Access → Distribution connections
    assignments = {0: 0, 1: 0, 2: 0, 3: 0,   # SW 1-4 → Dist-A
                   4: 1, 5: 1, 6: 1, 7: 1,    # SW 5-8 → Dist-B
                   8: 2, 9: 2, 10:2, 11:2}    # SW 9-12 → Dist-C
    for sw_i, dist_i in assignments.items():
        line(ax, acc_xs[sw_i], acc_y + 0.14,
             dist_xs[dist_i], dist_y - 0.19, C_CAT6, lw=1.4)

    # ── Core switches (2, connected) ───────────────────────────────────────────
    core_y = 5.1
    core_xs = [3.8, 6.2]
    core_labels = ["CORE-1\nCisco Cat 9500", "CORE-2\nCisco Cat 9500"]
    for cx, cl in zip(core_xs, core_labels):
        draw_device(ax, cx, core_y, 1.4, 0.45, cl, C_CORE, fontsize=7)

    # Core-Core LAG bond (double line)
    for dy in [-0.04, 0.04]:
        line(ax, core_xs[0] + 0.70, core_y + dy,
             core_xs[1] - 0.70, core_y + dy, "#FF6F00", lw=2.5)
    ax.text(5.0, core_y + 0.15, "40GbE LAG Bond (StackWise Virtual)",
            ha="center", fontsize=6.5, color="#FF6F00", fontweight="bold")

    # Distribution → Core (dual uplinks — two lines each)
    for dx in dist_xs:
        for cx in core_xs:
            line(ax, dx, dist_y + 0.19, cx, core_y - 0.225, C_FIBER, lw=1.8)
    ax.text(1.5, 4.1, "Dual 10GbE OS2\nSMF Uplinks\n(ECMP)", fontsize=6.5,
            color=C_FIBER, fontweight="bold", ha="center")

    # CCTV switches
    draw_device(ax, 1.1, core_y, 0.9, 0.35, "CCTV-A\n(Circuit A)", C_CCTV, fontsize=6.5)
    draw_device(ax, 8.9, core_y, 0.9, 0.35, "CCTV-B\n(Circuit B)", C_CCTV, fontsize=6.5)
    line(ax, 1.1, core_y + 0.175, core_xs[0], core_y + 0.1, C_CCTV, lw=1.5)
    line(ax, 8.9, core_y + 0.175, core_xs[1], core_y + 0.1, C_CCTV, lw=1.5)

    # VLAN labels on key segments
    for i, vlan in enumerate(["VLAN 20", "VLAN 30"]):
        ax.text([1.3, 8.7][i], core_y - 0.35, vlan, ha="center", fontsize=6,
                color=C_CCTV, style="italic")

    # ── Firewall ───────────────────────────────────────────────────────────────
    fw_y = 6.3
    draw_device(ax, 5.0, fw_y, 1.4, 0.38, "Palo Alto PA-3220\nHardware Firewall", C_FW, fontsize=7)
    for cx in core_xs:
        line(ax, cx, core_y + 0.225, 5.0, fw_y - 0.19, C_FIBER, lw=1.8)

    # ── Border router ─────────────────────────────────────────────────────────
    rtr_y = 7.35
    draw_device(ax, 5.0, rtr_y, 1.5, 0.38, "Cisco ASR 1001-X\nBorder Router", C_ROUTER, fontsize=7)
    line(ax, 5.0, fw_y + 0.19, 5.0, rtr_y - 0.19, C_FW, lw=2.0)
    ax.text(5.35, 6.82, "VLAN 60\n(DMZ/WAN)", fontsize=6, color=C_FW, style="italic")

    # ── WAN connections ────────────────────────────────────────────────────────
    # 100G WDM primary
    ax.annotate("", xy=(3.2, 7.9), xytext=(4.27, rtr_y + 0.0),
                arrowprops=dict(arrowstyle="-|>", color=C_WAN_PRI, lw=2.5))
    ax.text(2.6, 7.75, "100G DWDM WDM\n→ London HQ (Primary)", fontsize=7.5,
            color=C_WAN_PRI, fontweight="bold", ha="center")
    # 10G ISP secondary
    ax.annotate("", xy=(6.8, 7.9), xytext=(5.75, rtr_y + 0.0),
                arrowprops=dict(arrowstyle="-|>", color=C_WAN_ISP, lw=2.0))
    ax.text(7.4, 7.75, "10GBase-LR SFP+\n→ ISP (Backup)", fontsize=7.5,
            color=C_WAN_ISP, fontweight="bold", ha="center")

    # ── VLAN table ────────────────────────────────────────────────────────────
    vlan_data = [
        ("VLAN 10", "Operations", "48 PCs (12 rooms × 4)", C_ACCESS),
        ("VLAN 20", "CCTV-A",     "Surveillance Circuit A",  C_CCTV),
        ("VLAN 30", "CCTV-B",     "Surveillance Circuit B",  C_CCTV),
        ("VLAN 40", "PhySec",     "Electronic locks / Panic rooms", "#BF360C"),
        ("VLAN 50", "Mgmt",       "OOB Network Management", "#37474F"),
        ("VLAN 60", "WAN/Border", "Firewall ↔ Router ↔ ISP", C_ROUTER),
    ]
    col_x = [0.18, 0.85, 1.55, 3.4]
    for row_i, (vid, vname, vdesc, vc) in enumerate(vlan_data):
        vy = 2.55 - row_i * 0.27
        ax.add_patch(patches.FancyBboxPatch((0.12, vy - 0.1), 3.6, 0.22,
                     boxstyle="round,pad=0.02", facecolor=vc, alpha=0.15,
                     edgecolor=vc, linewidth=0.8))
        ax.text(col_x[0], vy + 0.01, vid,   fontsize=6.5, color=vc, fontweight="bold")
        ax.text(col_x[1], vy + 0.01, vname, fontsize=6.5, color=C_BORDER)
        ax.text(col_x[2], vy + 0.01, vdesc, fontsize=6, color="#546E7A")
    ax.text(0.12, 2.8, "VLAN Segmentation", fontsize=7.5, fontweight="bold", color=C_BORDER)

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(color=C_CORE,   label="Core Switch — Cisco Catalyst 9500 (StackWise Virtual)"),
        mpatches.Patch(color=C_DIST,   label="Distribution Switch — Cisco Catalyst 9300-48P"),
        mpatches.Patch(color=C_ACCESS, label="Access Switch — Cisco Catalyst 9200L-48P"),
        mpatches.Patch(color=C_FW,     label="Hardware Firewall — Palo Alto PA-3220"),
        mpatches.Patch(color=C_ROUTER, label="Border Router — Cisco ASR 1001-X"),
        mpatches.Patch(color=C_CCTV,   label="CCTV Aggregation (Circuit A & B — isolated)"),
        Line2D([0],[0], color=C_FIBER, lw=2.5, label="OS2 SMF 10GbaseLR Dual Uplink (Redundant)"),
        Line2D([0],[0], color=C_CAT6, lw=2, label="Cat6A Access (1GbE to PCs)"),
        Line2D([0],[0], color=C_WAN_PRI, lw=2.5, label="100G DWDM WAN — Primary"),
        Line2D([0],[0], color=C_WAN_ISP, lw=2, label="10GBase-LR — ISP Backup"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=6.5,
              framealpha=0.93, edgecolor=C_BORDER,
              title="Legend", title_fontsize=7.5)

    out_path = os.path.join(OUT, "diagram2_logical_LAN.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[OK] {out_path}")
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
#  DIAGRAM 3 — Logical WAN (DWDM Optical Grid)
# ═══════════════════════════════════════════════════════════════════════════════

def diagram_logical_wan():
    fig, ax = plt.subplots(figsize=(16, 14))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("#0D1117")
    fig.patch.set_facecolor("#0D1117")

    # Dark theme for optical network
    ax.text(5, 8.65, "Safe House WAN — Logical Optical Network Diagram",
            ha="center", fontsize=15, fontweight="bold", color="white")
    ax.text(5, 8.35, "100G DWDM Coherent Optical Grid  |  Ciena 6500 ROADM Nodes  |  Cisco ASR 9000 Routers",
            ha="center", fontsize=8.5, color="#8B9DC3")

    # ── Node positions (2×3 grid) ─────────────────────────────────────────────
    #  top-left   top-right(HQ)
    #  mid-left   mid-right
    #  bot-left   bot-right
    #  (safe house)
    # Define nodes properly
    node_pos = {
        "city_a":   (2.2, 6.5),
        "hq":       (7.8, 6.5),
        "city_c":   (2.2, 4.0),
        "city_d":   (7.8, 4.0),
        "safehouse":(2.2, 1.5),
        "city_e":   (7.8, 1.5),
    }
    node_labels = {
        "city_a":    "City A\n(Transit)",
        "hq":        "City B\n(Main Premises\nLondon HQ)",
        "city_c":    "City C\n(Transit)",
        "city_d":    "City D\n(Transit)",
        "safehouse": "Safe House\n(Secure Site)",
        "city_e":    "City E\n(Transit)",
    }
    node_type = {
        "city_a":    "roadm",
        "hq":        "router_hq",
        "city_c":    "roadm",
        "city_d":    "roadm",
        "safehouse": "router_sh",
        "city_e":    "roadm",
    }

    # ── Links (6 spans in the 2×3 grid) ───────────────────────────────────────
    spans = [
        ("city_a",   "hq"),        # top horizontal
        ("city_c",   "city_d"),    # middle horizontal
        ("safehouse","city_e"),    # bottom horizontal
        ("city_a",   "city_c"),    # left vertical top-mid
        ("city_c",   "safehouse"), # left vertical mid-bot
        ("hq",       "city_d"),    # right vertical top-mid
        ("city_d",   "city_e"),    # right vertical mid-bot
    ]

    # Path A (safe house → city_e → city_d → hq) in green
    path_a = [("safehouse","city_e"), ("city_e","city_d"), ("city_d","hq")]
    # Path B (safe house → city_c → city_a → hq) in cyan
    path_b = [("safehouse","city_c"), ("city_c","city_a"), ("city_a","hq")]

    def is_in_path(n1, n2, path):
        return (n1, n2) in path or (n2, n1) in path

    for (n1, n2) in spans:
        x1, y1 = node_pos[n1]
        x2, y2 = node_pos[n2]
        mx, my = (x1+x2)/2, (y1+y2)/2

        if is_in_path(n1, n2, path_a):
            col, lw, lbl = "#00E676", 3.0, "Path A\n(Primary)"
        elif is_in_path(n1, n2, path_b):
            col, lw, lbl = "#00BCD4", 2.5, "Path B\n(Backup)"
        else:
            col, lw, lbl = "#455A64", 1.5, ""

        ax.plot([x1, x2], [y1, y2], color=col, lw=lw, zorder=2)

        # Span label
        ax.text(mx, my, "100G DWDM\nDP-QPSK", ha="center", va="center",
                fontsize=5.5, color="#B0BEC5", zorder=4,
                bbox=dict(facecolor="#1A237E", edgecolor="none", alpha=0.7, boxstyle="round,pad=0.15"))

    # Draw nodes
    for nid, (nx_, ny_) in node_pos.items():
        ntype = node_type[nid]
        if ntype == "roadm":
            col = C_ROADM
            shape_w, shape_h = 1.3, 0.6
            symbol = "ROADM"
        elif ntype == "router_hq":
            col = "#1A237E"
            shape_w, shape_h = 1.5, 0.72
            symbol = "ROUTER\n(ASR 9000)"
        else:  # router_sh
            col = "#B71C1C"
            shape_w, shape_h = 1.5, 0.72
            symbol = "ROUTER\n(ASR 9000)"

        outer = FancyBboxPatch((nx_ - shape_w/2 - 0.08, ny_ - shape_h/2 - 0.08),
                               shape_w + 0.16, shape_h + 0.16,
                               boxstyle="round,pad=0.05",
                               facecolor="none", edgecolor="#90CAF9", linewidth=2.0, zorder=5)
        ax.add_patch(outer)
        inner = FancyBboxPatch((nx_ - shape_w/2, ny_ - shape_h/2),
                               shape_w, shape_h,
                               boxstyle="round,pad=0.04",
                               facecolor=col, edgecolor="white", linewidth=1.2, zorder=6)
        ax.add_patch(inner)
        ax.text(nx_, ny_ + 0.08, symbol, ha="center", va="center",
                fontsize=7, color="white", fontweight="bold", zorder=7)

        # Node label below
        nlabel = node_labels[nid]
        txt_col = "#00E676" if nid == "safehouse" else "#00BCD4" if nid == "hq" else "#78909C"
        ax.text(nx_, ny_ - shape_h/2 - 0.22, nlabel, ha="center", va="top",
                fontsize=7.5, color=txt_col, fontweight="bold", zorder=7)

    # ── Ciena brand labels ─────────────────────────────────────────────────────
    for nid, (nx_, ny_) in node_pos.items():
        if node_type[nid] == "roadm":
            ax.text(nx_, ny_ - 0.04, "Ciena 6500", ha="center", va="center",
                    fontsize=5.5, color="#80CBC4", zorder=8)

    # ── Path annotation boxes ─────────────────────────────────────────────────
    for label, col, xpos, ypos, path_desc in [
        ("Path A (Primary)", "#00E676", 5.0, 0.95,
         "Safe House → City E → City D → London HQ"),
        ("Path B (Backup / Protection)", "#00BCD4", 5.0, 0.55,
         "Safe House → City C → City A → London HQ"),
    ]:
        ax.add_patch(patches.FancyBboxPatch((1.5, ypos - 0.12), 7.0, 0.28,
                     boxstyle="round,pad=0.04", facecolor="#1B2838",
                     edgecolor=col, linewidth=1.5, zorder=8))
        ax.text(5.0, ypos + 0.02, f"● {label}  —  {path_desc}",
                ha="center", va="center", fontsize=7.5, color=col, fontweight="bold", zorder=9)

    # ── Optical protection annotation ─────────────────────────────────────────
    ax.text(5.0, 0.22,
            "Optical Protection Switching: <50ms failover via GMPLS  |  "
            "ROADM wavelength rerouting — no service interruption",
            ha="center", fontsize=7, color="#90A4AE")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(color=C_ROADM,   label="ROADM Node — Ciena 6500 Packet-Optical Platform"),
        mpatches.Patch(color="#1A237E",  label="Endpoint Router — Cisco ASR 9000 (London HQ)"),
        mpatches.Patch(color="#B71C1C",  label="Endpoint Router — Cisco ASR 9000 (Safe House)"),
        Line2D([0],[0], color="#00E676", lw=3, label="Path A — Primary Active Path"),
        Line2D([0],[0], color="#00BCD4", lw=2.5, label="Path B — Pre-computed Backup Path"),
        Line2D([0],[0], color="#455A64", lw=1.5, label="DWDM Span (100G DP-QPSK, C-band)"),
    ]
    leg = ax.legend(handles=legend_items, loc="upper left", fontsize=7,
                    framealpha=0.9, edgecolor="#37474F",
                    facecolor="#1B2838",
                    title="Legend", title_fontsize=7.5, labelcolor="white")
    leg.get_title().set_color("white")

    out_path = os.path.join(OUT, "diagram3_logical_WAN.png")
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[OK] {out_path}")
    return out_path


if __name__ == "__main__":
    print("JARVIS — Generating network diagrams...")
    p1 = diagram_physical_lan()
    p2 = diagram_logical_lan()
    p3 = diagram_logical_wan()
    print("\nAll 3 diagrams generated successfully.")
    print(f"  1. {p1}")
    print(f"  2. {p2}")
    print(f"  3. {p3}")
