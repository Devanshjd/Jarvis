"""
JARVIS — draw.io Professional Network Diagram Generator
Generates 3 .drawio files with real Cisco network shapes:
  1. Physical LAN (floor plan)
  2. Logical LAN (3-tier hierarchy)
  3. Logical WAN (DWDM optical grid)
"""
import os, subprocess, sys, datetime, hashlib, random, string

OUT = os.path.dirname(os.path.abspath(__file__))
_cid = [1000]

def nid():
    _cid[0] += 1
    return str(_cid[0])

# ── Style helpers ──────────────────────────────────────────────────────────────
B = "sketch=0;html=1;pointerEvents=1;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;"

def sw_l3(fc="#036897"):
    return f"shape=mxgraph.cisco.switches.layer_3_switch;{B}fillColor={fc};strokeColor=#ffffff;strokeWidth=2;"

def sw_access(fc="#0277BD"):
    return f"shape=mxgraph.cisco.switches.workgroup_switch;{B}fillColor={fc};strokeColor=#ffffff;strokeWidth=2;"

def router(fc="#4A148C"):
    return f"shape=mxgraph.cisco.routers.router;{B}fillColor={fc};strokeColor=#ffffff;strokeWidth=2;"

def firewall(fc="#B71C1C"):
    return f"shape=mxgraph.cisco.firewalls.firewall;{B}fillColor={fc};strokeColor=#ffffff;strokeWidth=2;"

def pc_icon(fc="#546E7A"):
    return f"shape=mxgraph.cisco.computers_and_peripherals.pc;{B}fillColor={fc};strokeColor=#ffffff;strokeWidth=2;"

def server(fc="#004D40"):
    return f"shape=mxgraph.cisco.servers.standard_server;{B}fillColor={fc};strokeColor=#ffffff;strokeWidth=2;"

def room_style(fc="#DAE8FC", bc="#6C8EBF"):
    return f"rounded=1;whiteSpace=wrap;html=1;fillColor={fc};strokeColor={bc};strokeWidth=2.5;fontSize=12;fontStyle=1;verticalAlign=top;arcSize=3;"

def band_style(fc, bc):
    return f"rounded=1;whiteSpace=wrap;html=1;fillColor={fc};strokeColor={bc};strokeWidth=1.5;fontSize=11;fontStyle=1;verticalAlign=middle;opacity=60;arcSize=2;"

def lbl(fc="#333333", fs=10, bold=True):
    fw = "1" if bold else "0"
    return f"text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontStyle={fw};fontSize={fs};fontColor={fc};"

def edge_ortho(color, width=2, dashed=0, label_bg="#FFFFFF"):
    return (f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
            f"strokeColor={color};strokeWidth={width};dashed={dashed};"
            f"labelBackgroundColor={label_bg};labelBorderColor=none;fontSize=9;")

def edge_straight(color, width=2, dashed=0):
    return (f"rounded=0;html=1;strokeColor={color};strokeWidth={width};"
            f"dashed={dashed};edgeStyle=none;labelBackgroundColor=#FFFFFF;fontSize=9;")

# ── XML cell builders ─────────────────────────────────────────────────────────
def V(cid, label, x, y, w, h, style):
    esc = (label.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
               .replace('"',"&quot;"))
    return (f'    <mxCell id="{cid}" value="{esc}" style="{style}" '
            f'vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            f'</mxCell>\n')

def E(cid, label, src, tgt, style):
    esc = label.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    return (f'    <mxCell id="{cid}" value="{esc}" style="{style}" '
            f'edge="1" source="{src}" target="{tgt}" parent="1">'
            f'<mxGeometry relative="1" as="geometry"/>'
            f'</mxCell>\n')

def _rand_id(n=20):
    return ''.join(random.choice(string.ascii_letters + string.digits + '-_') for _ in range(n))

def wrap(cells, pw=2200, ph=1600, title="Diagram"):
    # Lucidchart-compatible mxfile format:
    #   - ISO-8601 timestamp with Z
    #   - etag attribute (20-char random)
    #   - version attribute (current draw.io release)
    #   - diagram id that is a proper random token (not "d1")
    iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    etag = _rand_id(20)
    diagram_id = _rand_id(20)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<mxfile host="app.diagrams.net" modified="{iso}" '
            f'agent="Mozilla/5.0 (JARVIS)" etag="{etag}" '
            f'version="24.7.17" type="device">\n'
            f'  <diagram id="{diagram_id}" name="{title}">\n'
            f'    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1" '
            f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="{pw}" pageHeight="{ph}" math="0" shadow="0">\n'
            f'      <root>\n'
            f'        <mxCell id="0" />\n'
            f'        <mxCell id="1" parent="0" />\n'
            f'{cells}      </root>\n'
            f'    </mxGraphModel>\n'
            f'  </diagram>\n'
            f'</mxfile>\n')


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAM 1 — Physical LAN
# ═══════════════════════════════════════════════════════════════════════════════
def build_physical_lan():
    _cid[0] = 1000
    c = ""

    # Title
    t = nid()
    c += V(t, "Safe House — Physical LAN Network Diagram",
           400, 20, 1400, 50,
           "text;html=1;strokeColor=none;fillColor=none;align=center;"
           "verticalAlign=middle;whiteSpace=wrap;rounded=0;fontStyle=1;"
           "fontSize=18;fontColor=#0D47A1;")
    t2 = nid()
    c += V(t2, "30m × 10m  |  Three-Layer Hierarchical Model  |  OS2 SMF Backbone + Cat6A Access",
           400, 70, 1400, 30,
           "text;html=1;strokeColor=none;fillColor=none;align=center;"
           "verticalAlign=middle;whiteSpace=wrap;rounded=0;fontStyle=0;"
           "fontSize=10;fontColor=#546E7A;")

    # Room layout: 4 rows (top=row3) × 3 cols
    # Room W=380 H=210, hgap=25, vgap=20
    # Canvas 2200 wide, start X = (2200-3*380-2*25)/2 = (2200-1190)/2 = 505
    RW, RH, HGAP, VGAP = 380, 210, 25, 20
    CX = [505, 505+RW+HGAP, 505+2*(RW+HGAP)]   # col left-x: 505, 910, 1315
    # Rows from top: row3=rooms 10,11,12 | row2=9,8,7 | row1=4,5,6 | row0=3,2,1
    RY = [110, 110+RH+VGAP, 110+2*(RH+VGAP), 110+3*(RH+VGAP)]
    # row3=110, row2=340, row1=570, row0=800

    rooms = [
        # (num, col_i, row_i, label, fc, bc)
        (1,  0, 3, "Room 1",              "#DAE8FC","#6C8EBF"),
        (2,  1, 3, "Room 2",              "#DAE8FC","#6C8EBF"),
        (3,  2, 3, "Room 3",              "#DAE8FC","#6C8EBF"),
        (4,  2, 2, "Room 4",              "#DAE8FC","#6C8EBF"),
        (5,  1, 2, "Room 5 (Panic Room)", "#FFCCBC","#E64A19"),
        (6,  0, 2, "Room 6",              "#DAE8FC","#6C8EBF"),
        (7,  0, 1, "Room 7",              "#DAE8FC","#6C8EBF"),
        (8,  1, 1, "Room 8 — Comms Room (Core Infrastructure)", "#FFF9C4","#F9A825"),
        (9,  2, 1, "Room 9",              "#DAE8FC","#6C8EBF"),
        (10, 2, 0, "Room 10",             "#DAE8FC","#6C8EBF"),
        (11, 1, 0, "Room 11",             "#DAE8FC","#6C8EBF"),
        (12, 0, 0, "Room 12",             "#DAE8FC","#6C8EBF"),
    ]

    room_ids = {}
    sw_ids   = {}

    for (num, ci, ri, lbl_text, fc, bc) in rooms:
        rx, ry = CX[ci], RY[ri]
        rid = nid()
        room_ids[num] = rid
        c += V(rid, lbl_text, rx, ry, RW, RH, room_style(fc, bc))

        cx_center = rx + RW//2
        cy_center = ry + RH//2 + 20

        if num == 8:
            # Core rack: Core-1, Core-2, Firewall, Router, CCTV-A, CCTV-B
            core1 = nid(); core2 = nid(); fw_id = nid()
            rtr_id = nid(); cctva = nid(); cctvb = nid()

            c += V(core1, "CORE-1&#xa;Cisco Cat 9500",
                   cx_center-120, cy_center-30, 65, 65, sw_l3("#B71C1C"))
            c += V(core2, "CORE-2&#xa;Cisco Cat 9500",
                   cx_center+55, cy_center-30, 65, 65, sw_l3("#B71C1C"))
            c += V(fw_id, "PA-3220&#xa;Firewall",
                   cx_center-25, cy_center-30, 50, 55, firewall())
            c += V(rtr_id, "ASR 1001-X&#xa;Border Router",
                   cx_center-25, cy_center+45, 50, 55, router())
            c += V(cctva, "CCTV-A", cx_center-155, cy_center+20, 45, 45, sw_access("#880E4F"))
            c += V(cctvb, "CCTV-B", cx_center+110, cy_center+20, 45, 45, sw_access("#880E4F"))

            # LAG bond label
            lag = nid()
            c += V(lag, "40GbE LAG Bond", cx_center-50, cy_center-55, 100, 20,
                   "text;html=1;strokeColor=none;fillColor=none;align=center;"
                   "verticalAlign=middle;fontStyle=1;fontSize=8;fontColor=#E65100;")
            # Store room8 core refs for later
            room_ids["core1"] = core1; room_ids["core2"] = core2
            room_ids["fw"] = fw_id;   room_ids["rtr"] = rtr_id
            room_ids["cctva"] = cctva; room_ids["cctvb"] = cctvb
            # Core-core LAG
            lag_edge = nid()
            c += E(lag_edge, "", core1, core2,
                   "edgeStyle=none;strokeColor=#FF6F00;strokeWidth=4;dashed=0;html=1;")
        else:
            # Access switch + 4 PCs
            swid = nid()
            sw_ids[num] = swid
            c += V(swid, f"SW-{num:02d}", cx_center-25, ry+40, 50, 50, sw_access())
            # 4 PCs
            for pi, px in enumerate([cx_center-140, cx_center-47, cx_center+47, cx_center+140]):
                pc = nid()
                c += V(pc, f"PC{pi+1}", px-18, ry+RH-65, 36, 36, pc_icon())

    # Distribution switches — placed in 5U satellite racks at strategic rooms
    # Dist-A in Room 3 (serves 1,2,3,4): right-center of Room 3
    # Dist-B in Room 7 (serves 5,6,7,8): left-center of Room 7
    # Dist-C in Room 11 (serves 9,10,11,12): center of Room 11
    dist_pos = {
        "Dist-A\n(Rooms 1-4)": (CX[2]+RW+30, RY[2]+RH//2-30, "#1B5E20"),
        "Dist-B\n(Rooms 5-8)": (CX[0]-160,   RY[1]+RH//2-30, "#1B5E20"),
        "Dist-C\n(Rooms 9-12)":(CX[1]+RW//2-30, RY[0]-130,   "#1B5E20"),
    }
    dist_ids = {}
    for dlbl, (dx, dy, dfc) in dist_pos.items():
        did = nid()
        dist_ids[dlbl.split("\n")[0]] = did
        c += V(did, dlbl, dx, dy, 60, 60, sw_l3(dfc))

    # Fibre edges: Core → Distribution (dual uplinks - 2 edges each)
    da = dist_ids["Dist-A"]; db = dist_ids["Dist-B"]; dc = dist_ids["Dist-C"]
    fiber_style  = edge_ortho("#E65100", 3, 0)
    fiber_style2 = edge_ortho("#E65100", 2, 1)
    cat6_style   = edge_ortho("#1565C0", 1.5, 0)

    for did, lbl_text in [(da,"10GbaseLR\nOS2 SMF"), (db,""), (dc,"")]:
        c += E(nid(), lbl_text, room_ids["core1"], did, fiber_style)
        c += E(nid(), "",       room_ids["core2"], did, fiber_style2)

    # Access switch → Distribution
    # Dist-A serves rooms 1,2,3,4
    for rn in [1, 2, 3, 4]:
        if rn in sw_ids:
            c += E(nid(), "Cat6A", sw_ids[rn], da, cat6_style)
    # Dist-B serves rooms 5,6,7
    for rn in [5, 6, 7]:
        if rn in sw_ids:
            c += E(nid(), "", sw_ids[rn], db, cat6_style)
    # Dist-C serves rooms 9,10,11,12
    for rn in [9, 10, 11, 12]:
        if rn in sw_ids:
            c += E(nid(), "", sw_ids[rn], dc, cat6_style)

    # Firewall ↔ Core link
    c += E(nid(), "VLAN 60", room_ids["fw"], room_ids["core1"],
           edge_straight("#E65100", 2))
    c += E(nid(), "", room_ids["fw"], room_ids["core2"],
           edge_straight("#E65100", 2))
    # Router ↔ Firewall
    c += E(nid(), "", room_ids["rtr"], room_ids["fw"],
           edge_straight("#4A148C", 2))

    # WAN connections from Router (going up/out of diagram)
    wan1 = nid(); wan2 = nid()
    c += V(wan1, "100G DWDM WDM\n→ London HQ (Primary)", 830, 10, 200, 60,
           "rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;"
           "strokeWidth=2;fontSize=10;fontStyle=1;fontColor=#2E7D32;")
    c += V(wan2, "10GBase-LR SFP+\n→ ISP Router (Backup)", 1120, 10, 200, 60,
           "rounded=1;whiteSpace=wrap;html=1;fillColor=#EDE7F6;strokeColor=#6A1B9A;"
           "strokeWidth=2;fontSize=10;fontStyle=1;fontColor=#6A1B9A;")
    c += E(nid(), "100Gbps", room_ids["rtr"], wan1,
           edge_straight("#2E7D32", 3, 0))
    c += E(nid(), "10Gbps",  room_ids["rtr"], wan2,
           edge_straight("#6A1B9A", 2, 0))

    # Legend box
    leg = nid()
    c += V(leg, "Legend", 50, 860, 240, 200,
           "rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#616161;"
           "strokeWidth=1.5;fontSize=12;fontStyle=1;verticalAlign=top;")
    leg_items = [
        ("OS2 SMF 10GbaseLR (Backbone)", "#E65100", "solid"),
        ("OS2 SMF Redundant Uplink",      "#E65100", "dashed"),
        ("Cat6A UTP (Access / 1GbE)",     "#1565C0", "solid"),
        ("100G DWDM WAN — Primary",       "#2E7D32", "solid"),
        ("10GBase-LR — ISP Backup",       "#6A1B9A", "solid"),
    ]
    for i, (ltxt, lc, _ls) in enumerate(leg_items):
        li = nid()
        c += V(li, f"— {ltxt}", 55, 885+i*30, 230, 25,
               f"text;html=1;strokeColor=none;fillColor=none;align=left;"
               f"verticalAlign=middle;fontStyle=0;fontSize=9;fontColor={lc};")

    return c


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAM 2 — Logical LAN
# ═══════════════════════════════════════════════════════════════════════════════
def build_logical_lan():
    _cid[0] = 3000
    c = ""

    PW, PH = 2000, 1600

    # Title
    c += V(nid(), "Safe House — Logical LAN Network Diagram",
           300, 20, 1400, 50,
           "text;html=1;strokeColor=none;fillColor=none;align=center;"
           "verticalAlign=middle;fontStyle=1;fontSize=18;fontColor=#0D47A1;")
    c += V(nid(), "Three-Layer Hierarchical Model  |  VLAN Segmentation  |  Dual-Path Redundancy  |  100% Availability",
           300, 68, 1400, 28,
           "text;html=1;strokeColor=none;fillColor=none;align=center;"
           "verticalAlign=middle;fontStyle=0;fontSize=10;fontColor=#546E7A;")

    # ── Layer bands ────────────────────────────────────────────────────────────
    bands = [
        ("WAN / EXTERNAL",   "#EDE7F6","#9C27B0", 100,  120,  1800, 100),
        ("BORDER LAYER",     "#FFF3E0","#F57C00", 220,  130,  1800, 90),
        ("CORE LAYER",       "#FFEBEE","#EF9A9A", 320,  130,  1800, 130),
        ("DISTRIBUTION",     "#E8F5E9","#A5D6A7", 460,  130,  1800, 130),
        ("ACCESS LAYER",     "#E3F2FD","#90CAF9", 600,  130,  1800, 280),
    ]
    for (blbl, bfc, bbc, by, bh_dummy, bw, bh) in bands:
        c += V(nid(), blbl, 100, by, bw, bh,
               band_style(bfc, bbc))

    # ── WAN boxes ─────────────────────────────────────────────────────────────
    wan1_id = nid(); wan2_id = nid()
    c += V(wan1_id, "100G DWDM WDM\n→ London HQ (Primary)",
           200, 120, 220, 70,
           "rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F5E9;strokeColor=#2E7D32;"
           "strokeWidth=2.5;fontSize=10;fontStyle=1;fontColor=#2E7D32;")
    c += V(wan2_id, "10GBase-LR SFP+\n→ ISP Router (Backup)",
           1580, 120, 220, 70,
           "rounded=1;whiteSpace=wrap;html=1;fillColor=#EDE7F6;strokeColor=#6A1B9A;"
           "strokeWidth=2.5;fontSize=10;fontStyle=1;fontColor=#6A1B9A;")

    # ── Border Router ─────────────────────────────────────────────────────────
    rtr_id = nid()
    c += V(rtr_id, "Cisco ASR 1001-X\nBorder Router",
           900, 230, 80, 80, router())
    c += E(nid(), "100Gbps Primary", wan1_id, rtr_id,
           edge_straight("#2E7D32", 3))
    c += E(nid(), "10Gbps Backup",   wan2_id, rtr_id,
           edge_straight("#6A1B9A", 2))

    # ── Firewall ──────────────────────────────────────────────────────────────
    fw_id = nid()
    c += V(fw_id, "Palo Alto PA-3220\nHardware Firewall",
           900, 340, 80, 80, firewall())
    c += E(nid(), "VLAN 60 (WAN/Border)", rtr_id, fw_id,
           edge_straight("#4A148C", 2))

    # ── Core switches ─────────────────────────────────────────────────────────
    core1_id = nid(); core2_id = nid()
    c += V(core1_id, "CORE-1\nCisco Cat 9500\n(StackWise Virtual)",
           660, 470, 80, 80, sw_l3("#B71C1C"))
    c += V(core2_id, "CORE-2\nCisco Cat 9500\n(StackWise Virtual)",
           1140, 470, 80, 80, sw_l3("#B71C1C"))

    # LAG bond
    c += E(nid(), "40GbE LAG Bond (StackWise Virtual)", core1_id, core2_id,
           "edgeStyle=none;strokeColor=#FF6F00;strokeWidth=5;dashed=0;html=1;"
           "fontSize=9;labelBackgroundColor=#FFFFFF;")

    # Firewall → both cores
    c += E(nid(), "", fw_id, core1_id, edge_straight("#B71C1C", 2))
    c += E(nid(), "", fw_id, core2_id, edge_straight("#B71C1C", 2))

    # CCTV switches
    cctva_id = nid(); cctvb_id = nid()
    c += V(cctva_id, "CCTV-A\nCircuit A",  350, 470, 65, 65, sw_access("#880E4F"))
    c += V(cctvb_id, "CCTV-B\nCircuit B", 1460, 470, 65, 65, sw_access("#880E4F"))
    c += E(nid(), "VLAN 20", cctva_id, core1_id, edge_straight("#880E4F", 1.5))
    c += E(nid(), "VLAN 30", cctvb_id, core2_id, edge_straight("#880E4F", 1.5))

    # ── Distribution switches ─────────────────────────────────────────────────
    dist_xs = [450, 900, 1350]
    dist_lbls = ["Dist-A\n(Rooms 1-4)", "Dist-B\n(Rooms 5-8)", "Dist-C\n(Rooms 9-12)"]
    dist_ids_list = []
    for dx, dlbl in zip(dist_xs, dist_lbls):
        did = nid()
        dist_ids_list.append(did)
        c += V(did, dlbl, dx, 610, 70, 70, sw_l3("#1B5E20"))
        # Dual uplinks to both cores
        c += E(nid(), "10GbE OS2 SMF", did, core1_id,
               edge_ortho("#E65100", 2, 0))
        c += E(nid(), "Redundant", did, core2_id,
               edge_ortho("#E65100", 1.5, 1))

    # ── Access switches (12) ─────────────────────────────────────────────────
    acc_xs = [i * 150 + 100 for i in range(12)]  # spread across bottom
    acc_lbls = [f"SW-{i+1:02d}\nVLAN 10/40" for i in range(12)]
    acc_dist  = [0,0,0,0, 1,1,1,1, 2,2,2,2]  # which dist each connects to

    for i, (ax, albl, di) in enumerate(zip(acc_xs, acc_lbls, acc_dist)):
        aid = nid()
        c += V(aid, albl, ax, 750, 55, 55, sw_access())
        c += E(nid(), "", aid, dist_ids_list[di],
               edge_ortho("#1565C0", 1.5, 0))

    # ── VLAN table ─────────────────────────────────────────────────────────────
    vlan_rows = [
        ("VLAN 10", "Operations",  "48 PCs (12 rooms × 4)",     "#0D47A1"),
        ("VLAN 20", "CCTV-A",      "Surveillance Circuit A",    "#880E4F"),
        ("VLAN 30", "CCTV-B",      "Surveillance Circuit B",    "#880E4F"),
        ("VLAN 40", "PhySec",      "Electronic locks / Panic",  "#BF360C"),
        ("VLAN 50", "Mgmt",        "OOB Management",            "#37474F"),
        ("VLAN 60", "WAN/Border",  "Firewall ↔ Router ↔ ISP",  "#4A148C"),
    ]
    c += V(nid(), "VLAN Segmentation", 1620, 600, 280, 25,
           "text;html=1;strokeColor=none;fillColor=none;align=left;"
           "verticalAlign=middle;fontStyle=1;fontSize=11;fontColor=#0D47A1;")
    for i, (vid, vname, vdesc, vc) in enumerate(vlan_rows):
        c += V(nid(), f"{vid} — {vname}: {vdesc}",
               1620, 625+i*32, 280, 28,
               f"rounded=1;whiteSpace=wrap;html=1;fillColor={vc}22;"
               f"strokeColor={vc};strokeWidth=1;fontSize=9;fontColor={vc};"
               f"fontStyle=1;align=left;spacingLeft=5;")

    return c


# ═══════════════════════════════════════════════════════════════════════════════
# DIAGRAM 3 — Logical WAN
# ═══════════════════════════════════════════════════════════════════════════════
def build_logical_wan():
    _cid[0] = 5000
    c = ""

    PW, PH = 1800, 1400

    # Dark background
    c += V(nid(), "", 0, 0, PW, PH,
           "rounded=0;whiteSpace=wrap;html=1;fillColor=#0D1117;strokeColor=none;")

    # Title
    c += V(nid(), "Safe House WAN — Logical Optical Network Diagram",
           200, 30, 1400, 50,
           "text;html=1;strokeColor=none;fillColor=none;align=center;"
           "verticalAlign=middle;fontStyle=1;fontSize=18;fontColor=#E3F2FD;")
    c += V(nid(), "100G DWDM Coherent Optical Grid  |  Ciena 6500 ROADM Nodes  |  Cisco ASR 9000 Routers",
           200, 78, 1400, 28,
           "text;html=1;strokeColor=none;fillColor=none;align=center;"
           "verticalAlign=middle;fontStyle=0;fontSize=10;fontColor=#78909C;")

    # Node positions: 2×3 grid
    # Col: left=400, right=1200   Row: top=200, mid=600, bot=1000
    NW, NH = 140, 100
    positions = {
        "city_a":    (330,  200),
        "hq":        (1200, 200),
        "city_c":    (330,  600),
        "city_d":    (1200, 600),
        "safehouse": (330,  1000),
        "city_e":    (1200, 1000),
    }
    node_labels = {
        "city_a":    "City A\n(Transit ROADM)\nCiena 6500",
        "hq":        "City B\nMain Premises\nLondon HQ\nCisco ASR 9000",
        "city_c":    "City C\n(Transit ROADM)\nCiena 6500",
        "city_d":    "City D\n(Transit ROADM)\nCiena 6500",
        "safehouse": "SAFE HOUSE\nSecure Site\nCisco ASR 9000",
        "city_e":    "City E\n(Transit ROADM)\nCiena 6500",
    }
    node_colors = {
        "city_a":    "#004D40",
        "hq":        "#1A237E",
        "city_c":    "#004D40",
        "city_d":    "#004D40",
        "safehouse": "#B71C1C",
        "city_e":    "#004D40",
    }
    node_ids = {}

    for nkey, (nx, ny) in positions.items():
        nid_v = nid()
        node_ids[nkey] = nid_v
        col = node_colors[nkey]
        nlbl = node_labels[nkey]
        if nkey in ("hq", "safehouse"):
            style = router(col)
        else:
            style = (f"shape=mxgraph.cisco.optical.optical_transport;"
                     f"sketch=0;html=1;fillColor={col};strokeColor=#00BCD4;"
                     f"strokeWidth=2;verticalLabelPosition=bottom;verticalAlign=top;"
                     f"align=center;outlineConnect=0;")
        c += V(nid_v, nlbl, nx, ny, NW, NH, style)

    # Links (7 spans)
    spans = [
        ("city_a",    "hq",       "Path B", "#00BCD4", 3, 0),
        ("city_c",    "city_d",   "",       "#455A64", 1.5, 0),
        ("safehouse", "city_e",   "Path A", "#00E676", 3, 0),
        ("city_a",    "city_c",   "Path B", "#00BCD4", 3, 0),
        ("city_c",    "safehouse","Path B", "#00BCD4", 3, 0),
        ("hq",        "city_d",   "Path A", "#00E676", 3, 0),
        ("city_d",    "city_e",   "Path A", "#00E676", 3, 0),
    ]

    for (n1, n2, elbl, ecol, ew, ed) in spans:
        span_lbl = f"100G DWDM\nDP-QPSK" if not elbl else f"{elbl}\n100G DWDM"
        c += E(nid(), span_lbl, node_ids[n1], node_ids[n2],
               f"edgeStyle=none;html=1;strokeColor={ecol};strokeWidth={ew};"
               f"dashed={ed};fontSize=8;fontColor=#90A4AE;"
               f"labelBackgroundColor=#1A2332;labelBorderColor=none;")

    # Path legend boxes
    c += V(nid(),
           "● Path A (Primary Active): Safe House → City E → City D → London HQ",
           250, 1150, 1300, 40,
           "rounded=1;whiteSpace=wrap;html=1;fillColor=#0A1F0A;strokeColor=#00E676;"
           "strokeWidth=2;fontSize=11;fontStyle=1;fontColor=#00E676;")
    c += V(nid(),
           "● Path B (Pre-computed Backup): Safe House → City C → City A → London HQ",
           250, 1200, 1300, 40,
           "rounded=1;whiteSpace=wrap;html=1;fillColor=#0A1A25;strokeColor=#00BCD4;"
           "strokeWidth=2;fontSize=11;fontStyle=1;fontColor=#00BCD4;")
    c += V(nid(),
           "Optical Protection Switching: &lt;50ms failover via GMPLS  |  "
           "ROADM wavelength rerouting — no service interruption",
           250, 1250, 1300, 35,
           "text;html=1;strokeColor=none;fillColor=none;align=center;"
           "verticalAlign=middle;fontStyle=0;fontSize=9;fontColor=#78909C;")

    # Legend
    legend_items = [
        ("ROADM Node — Ciena 6500",            "#004D40"),
        ("Endpoint Router — Cisco ASR 9000 (HQ)",    "#1A237E"),
        ("Endpoint Router — Cisco ASR 9000 (Safe House)", "#B71C1C"),
        ("Path A: Primary Active",             "#00E676"),
        ("Path B: Pre-computed Backup",        "#00BCD4"),
        ("Unused DWDM Span",                   "#455A64"),
    ]
    c += V(nid(), "Legend", 30, 200, 270, 25,
           "text;html=1;strokeColor=none;fillColor=none;align=left;"
           "verticalAlign=middle;fontStyle=1;fontSize=11;fontColor=#E3F2FD;")
    for i, (ltxt, lc) in enumerate(legend_items):
        c += V(nid(), f"■ {ltxt}", 30, 228+i*30, 270, 25,
               f"text;html=1;strokeColor=none;fillColor=none;align=left;"
               f"verticalAlign=middle;fontStyle=0;fontSize=9;fontColor={lc};")

    return c


# ═══════════════════════════════════════════════════════════════════════════════
# Write files
# ═══════════════════════════════════════════════════════════════════════════════
def save(filename, cells_xml, title, pw=2200, ph=1200):
    path = os.path.join(OUT, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(wrap(cells_xml, pw, ph, title))
    print(f"[OK] {path}")
    return path

if __name__ == "__main__":
    print("JARVIS — Generating draw.io diagrams with Cisco network shapes...")
    p1 = save("LAN_Physical.drawio",  build_physical_lan(),
              "Physical LAN Diagram", 2200, 1200)
    p2 = save("LAN_Logical.drawio",   build_logical_lan(),
              "Logical LAN Diagram",  2000, 1050)
    p3 = save("WAN_Logical.drawio",   build_logical_wan(),
              "Logical WAN Diagram",  1800, 1400)

    # Find draw.io executable and open all 3 files
    drawio_paths = [
        r"C:\Program Files\draw.io\draw.io.exe",
        r"C:\Program Files (x86)\draw.io\draw.io.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\draw.io\draw.io.exe"),
    ]
    drawio_exe = None
    for dp in drawio_paths:
        if os.path.exists(dp):
            drawio_exe = dp
            break

    all_files = [p1, p2, p3]

    # Export each .drawio to PNG and PDF using draw.io CLI so user has
    # a guaranteed-working copy even if Lucidchart rejects the XML.
    png_files, pdf_files = [], []
    if drawio_exe:
        print(f"\n[JARVIS] Exporting PNG + PDF via draw.io CLI...")
        for path in all_files:
            base = os.path.splitext(path)[0]
            png_path = base + ".png"
            pdf_path = base + ".pdf"
            try:
                subprocess.run(
                    [drawio_exe, "--export", "--format", "png",
                     "--scale", "2", "--border", "20",
                     "--output", png_path, path],
                    timeout=90, check=False,
                )
                if os.path.exists(png_path):
                    print(f"[OK] {png_path}")
                    png_files.append(png_path)
                subprocess.run(
                    [drawio_exe, "--export", "--format", "pdf",
                     "--border", "20", "--output", pdf_path, path],
                    timeout=90, check=False,
                )
                if os.path.exists(pdf_path):
                    print(f"[OK] {pdf_path}")
                    pdf_files.append(pdf_path)
            except Exception as e:
                print(f"[WARN] Export failed for {path}: {e}")

        print(f"\n[JARVIS] Opening diagrams in draw.io desktop for review...")
        for path in all_files:
            subprocess.Popen([drawio_exe, path])
    else:
        print("\n[JARVIS] draw.io not found in standard paths.")
        print(f"  Install: winget install JGraph.Draw")
        import webbrowser
        for path in all_files:
            webbrowser.open(path)

    print("\n" + "="*70)
    print(" FILES READY")
    print("="*70)
    print("\nLucidchart import (primary path):")
    print("  1. Open Lucidchart -> File -> Import Diagram")
    print("  2. Select 'Draw.io (.drawio)' as file type")
    print("  3. Upload one of these files:")
    for p in all_files:
        print(f"       {p}")
    if png_files:
        print("\nFallback (use PNG/PDF if Lucidchart still rejects):")
        for p in png_files + pdf_files:
            print(f"       {p}")
        print("  -> Insert PNGs directly into Word / submit as-is")
    print("\nAll files saved in:", OUT)
