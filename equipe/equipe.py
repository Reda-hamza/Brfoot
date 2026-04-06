import streamlit as st
import json
import random
import gspread
import io
import asyncio
from datetime import datetime
from telegram import Bot
from google.oauth2 import service_account

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, PathPatch
from matplotlib.path import Path
import matplotlib.patheffects as pe

# ─── CONFIGURATION ET STYLE ───────────────────────────────────────────────────
st.set_page_config(page_title="⚽ Team Generator Pro", page_icon="⚽", layout="wide")

st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #0a1628, #0e2040, #0a1628); }
    .main-header { text-align: center; padding: 20px; }
    .main-header h1 {
        font-size: 2.5rem; font-weight: 800;
        background: linear-gradient(135deg, #4a9eff, #a8d8ff);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .user-badge {
        background: rgba(74,158,255,0.15); border: 1px solid rgba(74,158,255,0.3);
        border-radius: 50px; padding: 7px 22px;
        display: inline-block; color: #a8d8ff; font-size: 15px;
    }
    .stButton > button {
        background: linear-gradient(135deg, #1a4a8a, #2563b0);
        color: white; border: 1px solid rgba(74,158,255,0.4);
        border-radius: 12px; padding: 12px 35px;
        font-weight: 700; font-size: 15px; transition: all 0.3s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(74,158,255,0.25);
        border-color: rgba(74,158,255,0.7);
    }
    .team-card {
        background: rgba(14,42,92,0.80); border-radius: 14px;
        padding: 16px; margin: 8px 0;
        border: 1px solid rgba(74,158,255,0.20);
    }
    .team-red-card   { border-left: 4px solid #e74c3c; }
    .team-green-card { border-left: 4px solid #27ae60; }
    .player-item {
        background: rgba(255,255,255,0.06); border-radius: 9px;
        padding: 7px 14px; margin: 6px 0;
        display: flex; align-items: center; transition: all 0.2s;
    }
    .player-item:hover { background: rgba(255,255,255,0.10); transform: translateX(4px); }
    .player-num {
        width: 26px; height: 26px; border-radius: 50%;
        display: inline-flex; align-items: center; justify-content: center;
        font-weight: bold; font-size: 12px; margin-right: 11px; flex-shrink: 0;
    }
    .num-red   { background: #e74c3c; color: white; }
    .num-green { background: #27ae60; color: white; }
    .footer { text-align: center; color: rgba(74,158,255,0.35); padding: 20px; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ─── DESSIN TERRAIN ET MAILLOTS ───────────────────────────────────────────────
_BG, _PITCH_D, _PITCH_L, _LINE_C, _RED_C, _GRN_C = "#0a1628", "#0e2a5c", "#112f6e", "#4a9eff", "#e74c3c", "#27ae60"

_POS_RED = [(0.50, 0.07), (0.20, 0.25), (0.80, 0.25), (0.22, 0.42), (0.78, 0.42), (0.50, 0.33)]
_POS_GRN = [(0.50, 0.93), (0.20, 0.75), (0.80, 0.75), (0.22, 0.58), (0.78, 0.58), (0.50, 0.67)]

def _draw_jersey(ax, cx, cy, name, color, s=0.056):
    h, hw, bw, sw, sh = s * 1.30, s * 0.82, s * 1.00, s * 0.50, s * 0.34
    my = cy + h * 0.16
    MV, LN, CL = Path.MOVETO, Path.LINETO, Path.CLOSEPOLY
    vb = [(cx-hw, cy+h/2), (cx+hw, cy+h/2), (cx+bw, cy-h/2), (cx-bw, cy-h/2), (cx-hw, cy+h/2)]
    ax.add_patch(PathPatch(Path(vb, [MV,LN,LN,LN,CL]), fc=color, ec='white', lw=0.9, zorder=5))
    vl = [(cx-hw, my+sh*.5), (cx-hw-sw, my), (cx-hw-sw*.6, my-sh*.6), (cx-hw, my-sh*.3), (cx-hw, my+sh*.5)]
    ax.add_patch(PathPatch(Path(vl, [MV,LN,LN,LN,CL]), fc=color, ec='white', lw=0.9, zorder=4))
    vr = [(cx+hw, my+sh*.5), (cx+hw+sw, my), (cx+hw+sw*.6, my-sh*.6), (cx+hw, my-sh*.3), (cx+hw, my+sh*.5)]
    ax.add_patch(PathPatch(Path(vr, [MV,LN,LN,LN,CL]), fc=color, ec='white', lw=0.9, zorder=4))
    ax.add_patch(patches.Arc((cx, cy+h/2), hw*0.55, h*0.24, angle=0, theta1=180, theta2=360, color='white', lw=1.3, zorder=6))
    short = name[:8] + "." if len(name) > 8 else name
    ax.text(cx, cy - h/2 - 0.022, short, ha='center', va='top', fontsize=7.2, fontweight='bold', color='white', zorder=8, path_effects=[pe.withStroke(linewidth=2.2, foreground='black')])

def _draw_pitch(ax):
    ax.add_patch(patches.Rectangle((0,0), 1, 1, color=_PITCH_D, zorder=0))
    for i in range(6): 
        if i % 2 == 0: ax.add_patch(patches.Rectangle((0, i/6), 1, 1/6, color=_PITCH_L, zorder=0))
    lw, kw = 1.5, dict(color=_LINE_C, lw=1.5, zorder=2, alpha=0.72)
    ax.plot([.04,.96,.96,.04,.04], [.02,.02,.98,.98,.02], **kw)
    ax.plot([.04,.96], [.50,.50], **kw)
    ax.add_patch(patches.Ellipse((.50,.50), .38, .13, ec=_LINE_C, fc='none', lw=lw, alpha=0.72, zorder=2))
    ax.plot(.50,.50, 'o', color=_LINE_C, ms=3)
    ax.plot([.24,.24,.76,.76], [.02,.18,.18,.02], **kw)
    ax.plot([.24,.24,.76,.76], [.98,.82,.82,.98], **kw)

def generate_lineup_image(team_a, team_b, week_label=""):
    fig = plt.figure(figsize=(6.5, 11), facecolor=_BG, dpi=160)
    ax_h = fig.add_axes([0, 0.915, 1, 0.085])
    ax_h.axis('off')
    ax_h.text(.5, .65, "COMPOSITION", ha='center', fontsize=19, fontweight='bold', color='white')
    ax_h.text(.5, .18, week_label, ha='center', fontsize=8, color='#7fb3f5')
    ax = fig.add_axes([0.04, 0.085, 0.92, 0.83])
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis('off')
    _draw_pitch(ax)
    for (x,y), name in zip(_POS_RED, team_a): _draw_jersey(ax, x, y, name, _RED_C)
    for (x,y), name in zip(_POS_GRN, team_b): _draw_jersey(ax, x, y, name, _GRN_C)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=160, bbox_inches='tight', facecolor=_BG)
    plt.close(fig)
    return buf.getvalue()

# ─── TEAM GENERATOR CLASS ─────────────────────────────────────────────────────
class TeamGenerator:
    def __init__(self):
        # NOTE : Remplacez cet ID par l'ID de votre Google Sheet réel
        self.spreadsheet_id = "root-dispatch-470910-c2" 
        self.client = None
        self.notes_dict = {}
        self.linked_players = []
        self.load_notes()

    def load_notes(self):
        try:
            with open('notes_joureurs.json', 'r', encoding='utf-8') as f:
                self.notes_dict = {k.upper().strip(): int(v) for k, v in json.load(f).items()}
        except: self.notes_dict = {}

    def init_gspread_client(self):
        if self.client is None:
            try:
                creds_info = st.secrets["gcp_service_account"]
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = service_account.Credentials.from_service_account_info(creds_info, scopes=scope)
                self.client = gspread.authorize(creds)
                return True
            except Exception as e:
                st.error(f"Erreur connexion Google: {e}")
                return False
        return True

    def get_players_from_sheet(self, target_week):
        if not self.init_gspread_client(): return []
        try:
            sheet = self.client.open_by_key(self.spreadsheet_id).sheet1
            data = sheet.get_all_values()
            if not data: return []
            headers = [h.strip().lower() for h in data[0]]
            idx_sem = next((i for i, h in enumerate(headers) if "semaine" in h), -1)
            idx_pre = next((i for i, h in enumerate(headers) if "pres" in h), -1)
            idx_nom = next((i for i, h in enumerate(headers) if "prenom" in h), -1)
            
            present_players = []
            for row in data[1:]:
                if row[idx_sem].strip().lower() == target_week.lower() and row[idx_pre].strip().lower() in ["présent", "present"]:
                    name = row[idx_nom].strip().upper()
                    if "+" in name: present_players.extend([n.strip() for n in name.split("+")])
                    else: present_players.append(name)
            return list(dict.fromkeys(present_players))
        except: return []

    def generate_teams(self, players):
        team_a, team_b = [], []
        # Équilibrage simple
        pool = sorted(players, key=lambda x: self.notes_dict.get(x, 0), reverse=True)
        for i, p in enumerate(pool):
            if len(team_a) < 6 and (sum(self.notes_dict.get(n,0) for n in team_a) <= sum(self.notes_dict.get(n,0) for n in team_b) or len(team_b) >= 6):
                team_a.append(p)
            else: team_b.append(p)
        
        while len(team_a) < 6: team_a.append(f"Remplaçant A{len(team_a)+1}")
        while len(team_b) < 6: team_b.append(f"Remplaçant B{len(team_b)+1}")
        random.shuffle(team_a); random.shuffle(team_b)
        return team_a, team_b

    async def send_to_telegram(self, ta, tb, user_name, img_bytes):
        try:
            bot = Bot(token=st.secrets["TELEGRAM_BOT_TOKEN"])
            caption = f"⚽ Composition BRFOOT\nGenérée par : {user_name}\n\n🔴 ROUGE :\n" + \
                      "\n".join(f"- {p}" for p in ta) + "\n\n🟢 VERTE :\n" + "\n".join(f"- {p}" for p in tb)
            await bot.send_photo(chat_id=st.secrets["TELEGRAM_CHAT_ID"], photo=io.BytesIO(img_bytes), caption=caption)
            return True
        except Exception as e:
            st.error(f"Erreur Telegram: {e}")
            return False

# ─── INTERFACE STREAMLIT ──────────────────────────────────────────────────────
def main():
    st.markdown('<div class="main-header"><h1>⚽ TEAM GENERATOR BRFOOT ⚽</h1></div>', unsafe_allow_html=True)
    gen = TeamGenerator()
    user = st.query_params.get("user", "Joueur")
    st.markdown(f'<center><span class="user-badge">👋 Bienvenue, <strong>{user}</strong></span></center><br>', unsafe_allow_html=True)

    if 'current_teams' not in st.session_state:
        week = f"Semaine {datetime.now().isocalendar()[1]}"
        players = gen.get_players_from_sheet(week)
        if players:
            ta, tb = gen.generate_teams(players)
            st.session_state.current_teams = (ta, tb, week)
        else:
            st.warning("⚠️ Aucun joueur trouvé pour cette semaine dans le Sheets.")
            return

    ta, tb, week_lbl = st.session_state.current_teams

    col_btn1, col_btn2 = st.columns(2)
    if col_btn1.button("🔄 RÉGÉNÉRER"):
        st.session_state.pop('current_teams')
        st.rerun()
    
    if col_btn2.button("📤 ENVOYER TELEGRAM"):
        img = generate_lineup_image(ta, tb, week_lbl)
        if asyncio.run(gen.send_to_telegram(ta, tb, user, img)):
            st.success("Envoyé avec succès !")
            st.balloons()

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="team-card team-red-card"><h3 style="color:#e74c3c; text-align:center;">🔴 ROUGE</h3></div>', unsafe_allow_html=True)
        for i, p in enumerate(ta, 1):
            st.markdown(f'<div class="player-item"><div class="player-num num-red">{i}</div>{p}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="team-card team-green-card"><h3 style="color:#27ae60; text-align:center;">🟢 VERTE</h3></div>', unsafe_allow_html=True)
        for i, p in enumerate(tb, 1):
            st.markdown(f'<div class="player-item"><div class="player-num num-green">{i}</div>{p}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
