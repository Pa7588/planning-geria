# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import re
import json

# ─── CONFIG ───────────────────────────────────────────────────────────────────

CIBLES = [
    "M. Lejay", "E. Malavelle", "S. Potin", "H. Pommiers", "Q. Joussain",
    "D. Leculier", "J. Astrongatt", "C. Cazenave", "I. De Boisset", "L. Touya",
    "C. Destremau", "A. Kadhel", "L. Boureaux", "J. Silo", "M. Carriou",
    "V. Bannholtzer", "I. Aithamoudi", "P. Lorette", "E. Renucci", "E. Nicolas",
    "B. Guyot", "C. Petureau", "Y. Esteves", "I. Taha", "G. Gillodes",
    "M. Belhomme De Franqueville", "E. Salgues", "E. Villedieu", "S. Kassou",
    "R. Pettes", "A. Kielholz", "J. Peyres", "M. Gratesac", "C. Gorra",
    "C. Vasseur", "T. Bourot", "V. Simionesco", "S. Jaouen", "C. Vert",
    "C. Chauvin", "M. Bousquet", "M. Ajlani", "P. Chretien", "P. Messina",
]

PLANNINGS = {
    "geriatrie": "https://app.planning.lifen.health/external/plannings/55ed4e1c59041a69a363",
}

GITHUB_TOKEN = "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"
GITHUB_REPO  = "Pa7588/planning-geria"
GITHUB_FILE  = "commentaires.txt"

MOIS_FR = ["Janvier","Février","Mars","Avril","Mai","Juin",
           "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
MOIS_NUM = {m: i+1 for i, m in enumerate(MOIS_FR)}

NON_ATTRIBUE = {"non attribué", "r. planning urg toulouse"}
JOURS_SEMAINE = {"lun","mar","mer","jeu","ven","sam","dim"}

PARASITES = {
    "lifen planning", "créez votre compte", "voir les échanges",
    "télécharger", "du", "au", "actions", "ajouter vos indisponibilités",
    "plannings", "actifs", "terminés", "publié et disponible",
    "© 2014", "centre d'aide", "contacter le support", "suggérer une évolution",
    "fr", "en", "tableau de bord", "agenda", "échanges", "disponibilités",
}

POSTES_GERIA = {
    "garonne-soins palliatifs", "garonne-soins palliatifs-pum",
    "pug-albarède", "pug albarède", "pug rangueil", "pug-rangueil jf",
}

JOURS_FERIES = {
    date(2026, 5,  8), date(2026, 5, 14), date(2026, 5, 25),
    date(2026, 7, 14), date(2026, 8, 15), date(2026, 11, 1),
}

DEBUG = True

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def est_ferie(d):        return d in JOURS_FERIES
def est_samedi(d):       return d.weekday() == 5
def est_dim_ou_ferie(d): return d.weekday() == 6 or est_ferie(d)

def categoriser_geria(poste, jour_date):
    p = poste.lower()
    if 'jf' in p:
        return ('rouge', 'geria-jf')
    if est_dim_ou_ferie(jour_date):
        return ('rouge', 'geria-dim')
    elif est_samedi(jour_date):
        return ('jaune', 'geria-sam')
    else:
        return ('orange', 'geria-semaine')

def est_poste_geria(s):
    return s.lower().strip() in POSTES_GERIA

def est_nom_personne(s):
    return bool(re.match(r'^[A-Z]\.\s+[A-Z][a-zA-ZÀ-ÿ\s\-]+$', s))

# ─── FETCH ────────────────────────────────────────────────────────────────────

def fetch_planning(nom, url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        texte = soup.get_text('\n')
        if DEBUG:
            with open(f"debug_{nom}.txt", "w", encoding="utf-8") as f:
                f.write(texte)
        return texte
    except Exception as e:
        print(f"  ⚠ Erreur fetch {url}: {e}")
        return ""

# ─── PARSER ───────────────────────────────────────────────────────────────────

def parse_texte(texte):
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    resultats = []
    mois_courant = None
    jour_courant = None
    poste_courant = None

    for ligne in lignes:
        ligne_low = ligne.lower()
        if ligne_low in PARASITES: continue
        if any(ligne_low.startswith(p) for p in [
            "du ", "au ", "© ", "gardes urg", "urgences", "sauv été",
            "hopital", "hôpital", "chu ", "gardes gér",
        ]): continue
        if re.match(r'^\d+\s+nouvelles?\s+', ligne_low): continue
        if ligne in MOIS_FR:
            mois_courant = ligne
            poste_courant = None
            continue
        if mois_courant is None: continue
        if re.match(r'^\d{1,2}$', ligne):
            jour_courant = int(ligne)
            poste_courant = None
            continue
        if ligne_low in JOURS_SEMAINE: continue
        if est_nom_personne(ligne):
            if poste_courant and jour_courant and mois_courant:
                if ligne.lower() not in NON_ATTRIBUE:
                    resultats.append({
                        "mois": mois_courant, "jour": jour_courant,
                        "poste": poste_courant, "personne": ligne,
                    })
            poste_courant = None
            continue
        if est_poste_geria(ligne):
            poste_courant = ligne
            continue
    return resultats

# ─── PLANNING ─────────────────────────────────────────────────────────────────

def construire_planning(toutes_entrees):
    planning = {}
    for m in MOIS_FR:
        planning[m] = {}
        for d in range(1, 32):
            planning[m][d] = {
                nom: {"couleur": "vert", "postes": [], "repos": False}
                for nom in CIBLES
            }
    for e in toutes_entrees:
        nom = e["personne"]
        if nom not in CIBLES: continue
        mois, jour, poste = e["mois"], e["jour"], e["poste"]
        try:
            jour_date = date(2026, MOIS_NUM[mois], jour)
        except ValueError:
            continue
        cell = planning[mois][jour][nom]
        couleur, type_poste = categoriser_geria(poste, jour_date)
        if cell["repos"]:
            cell["postes"].append(f"⚠ {poste}")
            cell["couleur"] = "orange"
        elif not cell["postes"]:
            cell["couleur"] = couleur
            cell["postes"].append(poste)
        else:
            if poste not in cell["postes"]:
                cell["postes"].append(poste)
                cell["couleur"] = "orange"
        d_l = jour_date + timedelta(days=1)
        m_l = MOIS_FR[d_l.month - 1]
        j_l = d_l.day
        if m_l in planning and j_l in planning[m_l]:
            cell_r = planning[m_l][j_l][nom]
            if not cell_r["postes"]:
                cell_r["couleur"] = "jaune-repos"
                cell_r["postes"].append("Repos de garde")
                cell_r["repos"] = True
    return planning

# ─── HTML ─────────────────────────────────────────────────────────────────────

COULEURS = {
    "vert":        ("#1a6b3a", "#d4edda", "Libre"),
    "rouge":       ("#7f1d1d", "#fee2e2", "Garde dim/JF (24h)"),
    "jaune":       ("#78350f", "#fef3c7", "Garde sam (13h-8h30)"),
    "jaune-repos": ("#78350f", "#fef9e7", "Repos de garde"),
    "orange":      ("#7c2d12", "#ffedd5", "Stage + garde soir"),
}

def couleur_css(c):
    txt, bg, _ = COULEURS.get(c, ("#374151", "#f3f4f6", ""))
    return f"color:{txt};background:{bg};"

def nb_jours_mois(mois):
    if mois == "Février": return 28
    if mois in ["Avril","Juin","Septembre","Novembre"]: return 30
    return 31

def nom_court(n):
    parts = n.split(". ", 1)
    return parts[1].split()[0] if len(parts) > 1 else n

def generer_html(planning, date_maj):
    today = date.today()

    # Valeurs Python injectées proprement dans le JS
    gh_token = GITHUB_TOKEN
    gh_repo  = GITHUB_REPO
    gh_file  = GITHUB_FILE
    cibles_json = json.dumps(CIBLES, ensure_ascii=False)

    legende_html = "".join(
        f'<span class="leg-item" style="{couleur_css(c)}">{COULEURS[c][2]}</span>'
        for c in ["vert","rouge","jaune","jaune-repos","orange"]
    )
    mois_tabs = "".join(
        f'<button class="tab-btn" onclick="showMonth(\'{m}\')" id="tab-{m}">{m}</button>'
        for m in MOIS_FR
    )

    mois_sections = ""
    for mois in MOIS_FR:
        idx = MOIS_NUM[mois]
        try:
            premier = date(2026, idx, 1)
        except ValueError:
            continue
        decalage = premier.weekday()
        nb_j = nb_jours_mois(mois)
        a_donnees = any(
            planning[mois][d][n]["postes"]
            for d in range(1, nb_j+1) for n in CIBLES
        )
        jours_html = "".join('<div class="day-cell empty"></div>' for _ in range(decalage))
        for d in range(1, nb_j + 1):
            try:
                jour_date = date(2026, idx, d)
            except ValueError:
                continue
            is_we    = jour_date.weekday() >= 5
            is_ferie = jour_date in JOURS_FERIES
            is_today = jour_date == today
            slots = ""
            for nom in CIBLES:
                cell = planning[mois][d][nom]
                c = cell["couleur"]
                label = " + ".join(cell["postes"]) if cell["postes"] else "Libre"
                prenom = nom_court(nom)
                nom_attr = nom.replace('"', '&quot;')
                slots += (
                    f'<div class="slot" data-nom="{nom_attr}" style="{couleur_css(c)}" title="{nom_attr} — {label}">'
                    f'<span class="slot-name">{prenom}</span>'
                    f'<span class="slot-comment" data-nom="{nom_attr}"></span>'
                    f'<span class="slot-poste">{label}</span></div>'
                )
            we_class    = " weekend" if is_we else ""
            ferie_class = " ferie"   if is_ferie else ""
            today_class = " today"   if is_today else ""
            today_badge = "<span class='today-badge'>Aujourd'hui</span>" if is_today else ""
            ferie_badge = "<span class='ferie-badge'>JF</span>" if is_ferie else ""
            jours_html += (
                f'<div class="day-cell{we_class}{ferie_class}{today_class}">'
                f'<div class="day-num">{d}{ferie_badge}{today_badge}</div>{slots}</div>'
            )
        badge = "" if a_donnees else ' <span class="no-data">Pas de données</span>'
        mois_sections += f"""
        <div class="month-section" id="month-{mois}" style="display:none">
            <h2>{mois} 2026{badge}</h2>
            <div class="week-headers">
                <div>Lun</div><div>Mar</div><div>Mer</div>
                <div>Jeu</div><div>Ven</div>
                <div class="we-h">Sam</div><div class="we-h">Dim</div>
            </div>
            <div class="cal-grid">{jours_html}</div>
        </div>"""

    def _a_donnees(m):
        nb_j = nb_jours_mois(m)
        return any(planning[m][d][n]["postes"] for d in range(1, nb_j+1) for n in CIBLES)

    mois_courant = MOIS_FR[today.month - 1]
    mois_defaut = mois_courant if _a_donnees(mois_courant) else next(
        (m for m in MOIS_FR if _a_donnees(m)), MOIS_FR[0]
    )

    # On construit le HTML avec les vraies valeurs Python (pas de f-string imbriquées)
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Planning Gériatrie</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root { --bg:#0f1117; --surface:#1a1d27; --border:#2a2d3a; --text:#e8eaf0; --text-dim:#6b7280; --accent:#4f8ef7; --radius:8px; --today:#4f8ef7; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'DM Mono',monospace; background:var(--bg); color:var(--text); min-height:100vh; }
.header { padding:24px 40px; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
.header h1 { font-family:'Syne',sans-serif; font-size:2rem; font-weight:800; letter-spacing:-0.02em; flex:1; min-width:120px; }
.header-right { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.maj-badge { font-size:0.7rem; color:var(--text-dim); background:var(--surface); border:1px solid var(--border); padding:4px 10px; border-radius:20px; white-space:nowrap; }
.toggle-btn { font-family:'DM Mono',monospace; font-size:0.7rem; padding:6px 14px; border:1px solid var(--border); border-radius:20px; background:transparent; color:var(--text-dim); cursor:pointer; transition:all 0.15s; text-transform:uppercase; letter-spacing:0.08em; white-space:nowrap; }
.toggle-btn:hover { color:var(--text); border-color:var(--accent); }
.toggle-btn.active { background:var(--accent); color:white; border-color:var(--accent); }
.legende { padding:12px 40px; display:flex; gap:8px; flex-wrap:wrap; border-bottom:1px solid var(--border); }
.leg-item { font-size:0.65rem; padding:3px 8px; border-radius:4px; font-weight:500; letter-spacing:0.05em; text-transform:uppercase; }
.tabs { padding:12px 40px; display:flex; gap:6px; flex-wrap:wrap; border-bottom:1px solid var(--border); position:sticky; top:0; background:var(--bg); z-index:10; }
.tab-btn { font-family:'DM Mono',monospace; font-size:0.7rem; padding:6px 14px; border:1px solid var(--border); border-radius:20px; background:transparent; color:var(--text-dim); cursor:pointer; transition:all 0.15s; text-transform:uppercase; letter-spacing:0.08em; }
.tab-btn:hover { color:var(--text); border-color:var(--accent); }
.tab-btn.active { background:var(--accent); color:white; border-color:var(--accent); }
.content { padding:24px 40px 60px; }
.month-section h2 { font-family:'Syne',sans-serif; font-size:1.4rem; font-weight:800; margin-bottom:16px; display:flex; align-items:center; gap:12px; }
.no-data { font-size:0.65rem; color:var(--text-dim); background:var(--surface); border:1px solid var(--border); padding:3px 8px; border-radius:4px; }
.week-headers { display:grid; grid-template-columns:repeat(7,1fr); gap:4px; margin-bottom:4px; }
.week-headers div { text-align:center; font-size:0.65rem; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.1em; padding:4px; }
.week-headers .we-h { color:#6366f1; }
.cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:4px; }
.day-cell { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:6px; min-height:120px; }
.day-cell.empty { background:transparent; border-color:transparent; }
.day-cell.weekend { border-color:#2a2d4a; background:#1a1d30; }
.day-cell.ferie { border-color:#b45309; background:#1c1508; }
.day-cell.today { border:2px solid var(--today); box-shadow:0 0 8px #4f8ef733; }
.day-num { font-size:0.7rem; font-weight:500; color:var(--text-dim); margin-bottom:4px; display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
.day-cell.weekend .day-num { color:#6366f1; }
.day-cell.ferie .day-num { color:#f59e0b; }
.day-cell.today .day-num { color:var(--today); font-weight:700; }
.today-badge { font-size:0.5rem; background:var(--today); color:white; padding:1px 4px; border-radius:3px; text-transform:uppercase; }
.ferie-badge { font-size:0.5rem; background:#b45309; color:white; padding:1px 4px; border-radius:3px; text-transform:uppercase; }
.slot { border-radius:4px; padding:3px 5px; margin-bottom:3px; font-size:0.62rem; display:flex; flex-direction:column; gap:1px; line-height:1.3; cursor:pointer; }
.slot.hidden { display:none; }
.slot-name { font-weight:500; }
.slot-comment { font-size:0.58rem; font-style:italic; opacity:0.9; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.slot-comment:empty { display:none; }
.slot-poste { opacity:0.75; font-size:0.56rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.comment-panel { display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:24px; z-index:200; width:320px; box-shadow:0 20px 60px rgba(0,0,0,0.6); }
.comment-panel.open { display:block; }
.comment-panel h3 { font-family:'Syne',sans-serif; font-size:1rem; font-weight:800; margin-bottom:4px; }
.comment-panel .subtitle { font-size:0.65rem; color:var(--text-dim); margin-bottom:16px; }
.comment-panel textarea { width:100%; background:#0f1117; border:1px solid var(--border); border-radius:6px; color:var(--text); font-family:'DM Mono',monospace; font-size:0.8rem; padding:10px; resize:none; height:80px; outline:none; }
.comment-panel textarea:focus { border-color:var(--accent); }
.comment-char { font-size:0.6rem; color:var(--text-dim); text-align:right; margin-top:4px; margin-bottom:12px; }
.comment-actions { display:flex; gap:8px; justify-content:flex-end; }
.btn-save { font-family:'DM Mono',monospace; font-size:0.7rem; padding:7px 16px; background:var(--accent); color:white; border:none; border-radius:6px; cursor:pointer; }
.btn-save:hover { opacity:0.85; }
.btn-cancel { font-family:'DM Mono',monospace; font-size:0.7rem; padding:7px 16px; background:transparent; color:var(--text-dim); border:1px solid var(--border); border-radius:6px; cursor:pointer; }
.btn-delete { font-family:'DM Mono',monospace; font-size:0.7rem; padding:7px 12px; background:transparent; color:#e87070; border:1px solid #7f1d1d; border-radius:6px; cursor:pointer; margin-right:auto; }
.save-status { font-size:0.65rem; text-align:center; margin-top:10px; min-height:16px; }
.save-status.ok { color:#6bcf8f; }
.save-status.err { color:#e87070; }
.overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:199; }
.overlay.open { display:block; }
@media (max-width:900px) {
  .header,.legende,.tabs,.content { padding-left:16px; padding-right:16px; }
  .header h1 { font-size:1.4rem; }
  .cal-grid { grid-template-columns:repeat(7,minmax(0,1fr)); gap:2px; }
  .day-cell { padding:3px; min-height:90px; }
  .slot { font-size:0.55rem; }
  .slot-poste { display:none; }
  .comment-panel { width:90vw; }
}
</style>
</head>
<body>
<div class="overlay" id="overlay" onclick="closeComment()"></div>
<div class="comment-panel" id="commentPanel">
  <h3 id="panelNom"></h3>
  <div class="subtitle">Clic sur un slot pour modifier · max 40 caractères</div>
  <textarea id="panelTextarea" maxlength="40" placeholder="Ex: Bonne garde, motivé..." oninput="updateChar()"></textarea>
  <div class="comment-char"><span id="charCount">0</span>/40</div>
  <div class="comment-actions">
    <button class="btn-delete" onclick="deleteComment()">Supprimer</button>
    <button class="btn-cancel" onclick="closeComment()">Annuler</button>
    <button class="btn-save" onclick="saveComment()">Sauvegarder</button>
  </div>
  <div class="save-status" id="saveStatus"></div>
</div>
<div class="header">
  <h1>Planning Gériatrie</h1>
  <div class="header-right">
    <button class="toggle-btn" id="btnFilter" onclick="toggleFilter()">Avec commentaire</button>
    <div class="maj-badge">⟳ Mis à jour le """ + date_maj + """</div>
  </div>
</div>
<div class="legende">""" + legende_html + """</div>
<div class="tabs">""" + mois_tabs + """</div>
<div class="content">""" + mois_sections + """</div>
<script>
const GITHUB_TOKEN = '""" + gh_token + """';
const GITHUB_REPO  = '""" + gh_repo + """';
const GITHUB_FILE  = '""" + gh_file + """';
const CIBLES = """ + cibles_json + """;

let comments = {};
let fileSha = null;
let filterActive = false;
let currentNom = null;

async function loadComments() {
  try {
    const r = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/contents/${GITHUB_FILE}`,
      { headers: { Authorization: `token ${GITHUB_TOKEN}` } }
    );
    if (r.status === 404) { comments = {}; fileSha = null; applyComments(); return; }
    const data = await r.json();
    fileSha = data.sha;
    const txt = atob(data.content.replace(/\\n/g, ''));
    comments = {};
    txt.split('\\n').forEach(line => {
      const idx = line.indexOf(':');
      if (idx > 0) {
        const nom = line.substring(0, idx).trim();
        const com = line.substring(idx + 1).trim();
        if (nom && com) comments[nom] = com;
      }
    });
    applyComments();
  } catch(e) { console.error('Erreur chargement', e); }
}

function applyComments() {
  document.querySelectorAll('.slot-comment').forEach(el => {
    el.textContent = comments[el.dataset.nom] || '';
  });
  applyFilter();
}

async function saveToGithub() {
  const lines = Object.entries(comments)
    .filter(([,v]) => v.trim())
    .map(([k,v]) => `${k}:${v}`)
    .join('\\n');
  const content = btoa(unescape(encodeURIComponent(lines)));
  const body = { message: 'Commentaires mis a jour', content };
  if (fileSha) body.sha = fileSha;
  const r = await fetch(
    `https://api.github.com/repos/${GITHUB_REPO}/contents/${GITHUB_FILE}`,
    {
      method: 'PUT',
      headers: { Authorization: `token ${GITHUB_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }
  );
  const data = await r.json();
  if (data.content) fileSha = data.content.sha;
  return r.ok;
}

function openComment(nom) {
  currentNom = nom;
  document.getElementById('panelNom').textContent = nom;
  const ta = document.getElementById('panelTextarea');
  ta.value = comments[nom] || '';
  updateChar();
  document.getElementById('saveStatus').textContent = '';
  document.getElementById('commentPanel').classList.add('open');
  document.getElementById('overlay').classList.add('open');
  ta.focus();
}

function closeComment() {
  document.getElementById('commentPanel').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
  currentNom = null;
}

function updateChar() {
  document.getElementById('charCount').textContent = document.getElementById('panelTextarea').value.length;
}

async function saveComment() {
  const val = document.getElementById('panelTextarea').value.trim();
  const status = document.getElementById('saveStatus');
  status.textContent = 'Sauvegarde...';
  status.className = 'save-status';
  if (val) comments[currentNom] = val;
  else delete comments[currentNom];
  applyComments();
  const ok = await saveToGithub();
  if (ok) {
    status.textContent = '✓ Sauvegarde !';
    status.className = 'save-status ok';
    setTimeout(closeComment, 800);
  } else {
    status.textContent = '✗ Erreur - reessaie';
    status.className = 'save-status err';
  }
}

async function deleteComment() {
  delete comments[currentNom];
  applyComments();
  await saveToGithub();
  closeComment();
}

function toggleFilter() {
  filterActive = !filterActive;
  document.getElementById('btnFilter').classList.toggle('active', filterActive);
  applyFilter();
}

function applyFilter() {
  document.querySelectorAll('.slot').forEach(s => {
    if (filterActive) s.classList.toggle('hidden', !comments[s.dataset.nom]);
    else s.classList.remove('hidden');
  });
}

document.querySelectorAll('.slot').forEach(s => {
  s.addEventListener('click', () => openComment(s.dataset.nom));
});

function showMonth(m) {
  document.querySelectorAll('.month-section').forEach(el => el.style.display='none');
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  const sec = document.getElementById('month-' + m);
  const btn = document.getElementById('tab-' + m);
  if (sec) sec.style.display = 'block';
  if (btn) btn.classList.add('active');
  localStorage.setItem('planning_mois', m);
}

const savedMois = localStorage.getItem('planning_mois');
showMonth(savedMois || '""" + mois_defaut + """');
loadComments();
</script>
</body>
</html>"""

    return html

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("Génération du planning gériatrie...")
    toutes_entrees = []
    for nom, url in PLANNINGS.items():
        print(f"  -> Fetch {nom}...")
        texte = fetch_planning(nom, url)
        entrees = parse_texte(texte)
        cibles = [e for e in entrees if e["personne"] in CIBLES]
        print(f"     {len(entrees)} entrees, dont {len(cibles)} pour les cibles")
        toutes_entrees.extend(entrees)

    print(f"\n  Total : {len(toutes_entrees)} entrees")
    for nom in CIBLES:
        n = sum(1 for e in toutes_entrees if e["personne"] == nom)
        if n > 0:
            print(f"    {nom}: {n} entrees")

    planning = construire_planning(toutes_entrees)
    date_maj = datetime.now().strftime("%d/%m/%Y a %H:%M")
    html = generer_html(planning, date_maj)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nindex.html genere ({len(html)//1024} Ko)")

if __name__ == "__main__":
    main()
