import os
import re
import random
import subprocess
import mimetypes
import socket
import shutil
import time
import json
import threading
from urllib.parse import quote
from flask import Flask, render_template_string, redirect, url_for, send_file, request, jsonify, send_from_directory, Response
from openai import OpenAI

app = Flask(__name__)

# ====================== AYARLAR & PERSISTENCE ======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "static/settings.json")
THUMB_FOLDER = os.path.join(BASE_DIR, "static/thumbnails")
STATIC_FOLDER = os.path.join(BASE_DIR, "static")

default_settings = {
    "movie_path": "",
    "api_key": "",
    "language": "tr",
    "vlc_path": "/usr/bin/vlc"
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return {**default_settings, **json.load(f)}
        except: pass
    return default_settings

def save_settings(data):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

current_settings = load_settings()

for folder in [THUMB_FOLDER, STATIC_FOLDER]:
    if not os.path.exists(folder): os.makedirs(folder, exist_ok=True)

FAV_FILE = os.path.join(STATIC_FOLDER, "favorites.json")
VIEWS_FILE = os.path.join(STATIC_FOLDER, "views.json")

# ====================== I18N (DİL DESTEĞİ) ======================
TRANSLATIONS = {
    "tr": {
        "title": "MediaPulse - Medya Koleksiyonum",
        "search_placeholder": "Video ara...",
        "all": "Tümü",
        "favorites": "Favoriler",
        "shuffle": "Rastgele",
        "lights": "Işıklar",
        "settings": "Ayarlar",
        "views": "İzlenme",
        "next_video": "Sıradaki Video...",
        "cancel": "İptal Et",
        "partner_hello": "😈 Selam yakışıklım... Videonun keyfini çıkarıyor musun? 🔥",
        "write_here": "Yaz...",
        "close": "Kapat",
        "save": "Kaydet",
        "movie_path_label": "Medya Klasör Yolu",
        "api_key_label": "Grok API Anahtarı (xai-...)",
        "lang_label": "Dil",
        "scan_finished": "Tarama Bitti. {count} video bulundu.",
        "no_video": "Video bulunamadı. Lütfen ayarları kontrol edin.",
        "ai_status_ok": "✅ Grok AI Bağlantısı Hazır! 😈",
        "ai_status_err": "⚠️ AI Bağlantı Hatası",
    },
    "en": {
        "title": "MediaPulse - My Media Collection",
        "search_placeholder": "Search video...",
        "all": "All",
        "favorites": "Favorites",
        "shuffle": "Shuffle",
        "lights": "Lights",
        "settings": "Settings",
        "views": "Views",
        "next_video": "Next Video...",
        "cancel": "Cancel",
        "partner_hello": "😈 Hey handsome... Enjoying the video? 🔥",
        "write_here": "Type...",
        "close": "Close",
        "save": "Save",
        "movie_path_label": "Media Folder Path",
        "api_key_label": "Grok API Key (xai-...)",
        "lang_label": "Language",
        "scan_finished": "Scan Finished. {count} videos found.",
        "no_video": "No videos found. Please check settings.",
        "ai_status_ok": "✅ Grok AI Connection Ready! 😈",
        "ai_status_err": "⚠️ AI Connection Error",
    }
}

def T(key):
    lang = current_settings.get("language", "tr")
    return TRANSLATIONS.get(lang, TRANSLATIONS["tr"]).get(key, key)

# ====================== VERİ YÖNETİMİ ======================
def load_json(file, default):
    if os.path.exists(file):
        try:
            with open(file, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return default

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

favorites = load_json(FAV_FILE, [])
views = load_json(VIEWS_FILE, {})

# ====================== GROK ======================
ai_client = None
def init_ai():
    global ai_client
    api_key = current_settings.get("api_key")
    if api_key:
        try:
            ai_client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
            print(T("ai_status_ok"))
        except:
            print(T("ai_status_err"))
    else:
        ai_client = None

init_ai()
movies = []
all_tags = set()

# ====================== YARDIMCI ======================
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close()
        return ip
    except: return "127.0.0.1"
LOCAL_IP = get_local_ip()

def clean_filename(filename):
    name = os.path.splitext(filename)[0]
    return re.sub(r'[^a-zA-Z0-9ğüşıöçĞÜŞİÖÇ\s]', ' ', name).strip()

def extract_tags(filename):
    lower = filename.lower()
    tags = set()
    tag_map = {
        'Anal': ['anal', 'ass', 'butt'], 'Milf': ['milf', 'mom', 'mature'],
        'Teen': ['teen', '18', 'young'], 'Amateur': ['amateur', 'homemade'],
        'BBW': ['bbw', 'chubby'], 'Asian': ['asian', 'jap'],
        'Ebony': ['ebony', 'black'], 'Lesbian': ['lesbian', 'girlgirl'],
        'BDSM': ['bdsm', 'bondage'], 'Hardcore': ['hard', 'rough'],
        'Pov': ['pov'], 'Squirt': ['squirt']
    }
    for tag, keywords in tag_map.items():
        if any(k in lower for k in keywords): tags.add(tag)
    return list(tags) if tags else ["Genel"]

def generate_thumbnail(video_path, video_id):
    thumb_path = os.path.join(THUMB_FOLDER, f"thumb_{video_id}.jpg")
    if os.path.exists(thumb_path): return f"/thumbnails/thumb_{video_id}.jpg"
    
    if shutil.which("ffmpeg"):
        cmd = ['ffmpeg', '-ss', '00:00:05', '-i', video_path, '-vframes', '1', '-q:v', '2', '-y', thumb_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"/thumbnails/thumb_{video_id}.jpg" if os.path.exists(thumb_path) else 'https://via.placeholder.com/300x169/000?text=No+Img'

def scan_directory():
    global movies, all_tags
    movies = []
    all_tags = set()
    id_counter = 0
    movie_path = current_settings.get("movie_path")
    
    if movie_path and os.path.exists(movie_path):
        print(f"--- {T('movie_path_label')} TARANIYOR ---")
        for root, _, files in os.walk(movie_path):
            if "$RECYCLE.BIN" in root: continue
            for file in files:
                if file.lower().endswith(('.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mpg')):
                    full_path = os.path.join(root, file)
                    tags = extract_tags(file)
                    for t in tags: all_tags.add(t)
                    
                    movies.append({
                        'id': id_counter,
                        'code': os.path.splitext(file)[0][:8].upper(),
                        'title': clean_filename(file),
                        'filename': file,
                        'path': full_path,
                        'poster': generate_thumbnail(full_path, id_counter),
                        'tags': tags,
                        'views': views.get(str(id_counter), 0),
                        'fav': str(id_counter) in favorites
                    })
                    id_counter += 1
    
    movies.sort(key=lambda x: x['views'], reverse=True)
    all_tags = sorted(list(all_tags))
    print(T("scan_finished").format(count=len(movies)))

@app.template_filter('format_views')
def format_views(value): return f"{value:,}".replace(",", ".")

# ====================== HTML TEMPLATE ======================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ t('title') }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.6.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;700&family=Orbitron:wght@700;900&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
    <style>
        :root { 
            --orange: #ff9900; 
            --orange-glow: rgba(255, 153, 0, 0.5);
            --dark: #0a0a0b; 
            --glass: rgba(15, 15, 16, 0.85);
        }
        
        body { 
            background: var(--dark); 
            color: #efeff1; 
            font-family: 'Outfit', sans-serif; 
            transition: 0.4s; 
            padding-bottom: 80px;
            scroll-behavior: smooth;
        }

        .lights-off body { background: #000 !important; }
        .lights-off .navbar, .lights-off .movie-item { opacity: 0.05; filter: grayscale(100%); }

        /* --- PREMIUM NAVBAR --- */
        .navbar { 
            background: var(--glass); 
            border-bottom: 1px solid rgba(255, 255, 255, 0.06); 
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            padding: 12px 0;
            z-index: 2000;
        }

        /* --- MODERN BRANDING --- */
        .brand-container {
            display: flex;
            align-items: center;
            text-decoration: none;
            gap: 12px;
            position: relative;
        }

        .brand-logo {
            width: 42px;
            height: 42px;
            background: linear-gradient(135deg, #ff9900, #ffb347);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 20px var(--orange-glow);
            position: relative;
            overflow: hidden;
        }

        .brand-logo::after {
            content: "";
            position: absolute;
            width: 100%; height: 100%;
            background: linear-gradient(white, transparent);
            opacity: 0.3;
        }

        .brand-text {
            font-family: 'Orbitron', sans-serif;
            font-size: 1.6rem;
            font-weight: 900;
            letter-spacing: -1px;
            background: linear-gradient(to right, #fff, #888);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
            padding: 0;
        }

        .pulse-dot {
            width: 8px; height: 8px;
            background: var(--orange);
            border-radius: 50%;
            display: inline-block;
            margin-left: 2px;
            box-shadow: 0 0 10px var(--orange);
            animation: pulse-ring 1.5s cubic-bezier(0.455, 0.03, 0.515, 0.955) infinite;
        }

        @keyframes pulse-ring {
            0% { transform: scale(0.8); box-shadow: 0 0 0 0 rgba(255, 153, 0, 0.7); }
            70% { transform: scale(1.1); box-shadow: 0 0 0 10px rgba(255, 153, 0, 0); }
            100% { transform: scale(0.8); box-shadow: 0 0 0 0 rgba(255, 153, 0, 0); }
        }

        /* --- UI ELEMENTS --- */
        .search { 
            border-radius: 14px; 
            background: rgba(255, 255, 255, 0.05); 
            border: 1px solid rgba(255, 255, 255, 0.1); 
            padding: 10px 25px; 
            color: #fff; 
            width: 100%; 
            max-width: 450px; 
            transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .search:focus { 
            background: rgba(255, 255, 255, 0.08);
            border-color: var(--orange); 
            box-shadow: 0 0 0 4px rgba(255, 153, 0, 0.15); 
            outline: none; 
            transform: scale(1.02);
        }

        .btn-action {
            width: 42px; height: 42px;
            border-radius: 12px;
            display: flex; align-items: center; justify-content: center;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #fff;
            transition: 0.3s;
            cursor: pointer;
        }
        .btn-action:hover {
            background: rgba(255, 153, 0, 0.1);
            border-color: var(--orange);
            color: var(--orange);
            transform: translateY(-2px);
        }

        /* --- CARDS --- */
        .tag-btn { border: 1px solid rgba(255, 153, 0, 0.3) !important; background: transparent; color: var(--orange); border-radius: 12px; font-weight: 600; padding: 6px 18px; transition: 0.3s; margin-bottom: 5px; font-size: 0.9rem;}
        .tag-btn.active, .tag-btn:hover { background: var(--orange) !important; color: #fff !important; box-shadow: 0 4px 15px var(--orange-glow); }
        
        .movie-item { transition: 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); cursor: pointer; position: relative; }
        .movie-item:hover { transform: translateY(-10px) scale(1.02); z-index: 10; }
        
        .poster { aspect-ratio: 16/9; border-radius: 20px; overflow: hidden; position: relative; background: #111; border: 1px solid rgba(255, 255, 255, 0.05); }
        .poster img { width: 100%; height: 100%; object-fit: cover; transition: 0.6s; }
        .movie-item:hover img { filter: brightness(1.1) saturate(1.2); }
        
        .playov { position: absolute; inset: 0; background: radial-gradient(circle, rgba(255, 153, 0, 0.4) 0%, transparent 70%); opacity: 0; transition: 0.4s; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(2px); }
        .movie-item:hover .playov { opacity: 1; }
        
        .code { position: absolute; top: 12px; left: 12px; background: rgba(0,0,0,0.7); backdrop-filter: blur(5px); padding: 5px 10px; border-radius: 10px; font-weight: 700; font-size: 0.75rem; color: var(--orange); border: 1px solid rgba(255, 153, 0, 0.2); }
        
        .movie-title { font-weight: 600; font-size: 1rem; color: #fff; margin-top: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

        /* --- MODALS & PLAYER --- */
        .modal-content { border-radius: 24px; overflow: hidden; background: #121214 !important; border: 1px solid rgba(255, 255, 255, 0.08) !important; }
        .modal-header { border-bottom: 1px solid rgba(255, 255, 255, 0.05); padding: 20px; }
        .form-control, .form-select { background: #000 !important; border: 1px solid #333 !important; border-radius: 12px; padding: 12px; color: #fff !important; }
        .form-control:focus { border-color: var(--orange) !important; box-shadow: none; }

        @media(max-width:768px){ 
            .brand-text { font-size: 1.2rem; }
            .search { display: none; } 
        }
        #miniPlayer { background: #111; border-top: 3px solid var(--pink); z-index: 9999; height: 70px; }
        .chat-window { position: fixed; bottom: 80px; right: 20px; width: 350px; background: rgba(17,17,17,0.95); border: 2px solid var(--pink); border-radius: 10px; display: none; flex-direction: column; z-index: 2100 !important; backdrop-filter: blur(10px); }
        .nav-btn-overlay { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(0,0,0,0.5); color: white; border: 2px solid var(--pink); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; cursor: pointer; transition: 0.2s; z-index: 100; opacity: 0; }
        .modal-body:hover .nav-btn-overlay { opacity: 1; }
        .nav-btn-overlay:hover { background: var(--pink); transform: translateY(-50%) scale(1.1); }
        .prev-btn { left: 20px; }
        .next-btn { right: 20px; }
        .player-chat-btn { position: absolute; bottom: 20px; right: 20px; background: rgba(0,0,0,0.6); color: var(--pink); border: 2px solid var(--pink); padding: 10px 20px; border-radius: 30px; font-weight: bold; cursor: pointer; z-index: 101; transition: 0.2s; opacity: 0.6; }
        .modal-body:hover .player-chat-btn { opacity: 1; }
        .player-chat-btn:hover { background: var(--pink); color: white; }
    </style>
</head>
<body>

<nav class="navbar fixed-top">
    <div class="container-fluid d-flex align-items-center justify-content-between px-lg-5">
        <a href="/" class="brand-container">
            <div class="brand-logo">
                <i class="fas fa-play text-white" style="font-size: 1.2rem; margin-left: 3px;"></i>
            </div>
            <h1 class="brand-text">MediaPulse<span class="pulse-dot"></span></h1>
        </a>
        
        <input type="text" class="search d-none d-md-block" placeholder="{{ t('search_placeholder') }}" onkeyup="search(this.value)">
        
        <div class="d-flex gap-3">
            <div class="btn-action" onclick="toggleLights()" title="{{ t('lights') }}"><i class="fas fa-lightbulb"></i></div>
            <div class="btn-action" data-bs-toggle="modal" data-bs-target="#settingsModal" title="{{ t('settings') }}"><i class="fas fa-sliders-h"></i></div>
            <div class="btn-action" onclick="randomPlay()" title="{{ t('shuffle') }}" style="background: var(--orange); border:none;"><i class="fas fa-random"></i></div>
        </div>
    </div>
</nav>

<div class="container-fluid pt-5 mt-5 px-4">
    <div class="d-flex flex-wrap gap-2 justify-content-center mb-4">
        <button class="btn tag-btn active" onclick="filterTag('')">{{ t('all') }}</button>
        {% for tag in all_tags %}
        <button class="btn tag-btn" onclick="filterTag('{{tag}}')">{{tag}}</button>
        {% endfor %}
    </div>

    {% if movies|length == 0 %}
    <div class="text-center py-5">
        <h3 class="text-muted">{{ t('no_video') }}</h3>
        <button class="btn btn-danger mt-3" data-bs-toggle="modal" data-bs-target="#settingsModal">{{ t('settings') }}</button>
    </div>
    {% endif %}

    <div class="row row-cols-1 row-cols-sm-2 row-cols-md-3 row-cols-lg-4 row-cols-xl-5 g-4" id="grid">
        {% for m in movies %}
        <div class="col item" data-tags="{{' '.join(m.tags)|lower}}" data-title="{{m.title|lower}}" data-fav="{{ 'true' if m.fav else 'false' }}">
            <div class="movie-item" onclick="openPlayer({{m.id}},'{{m.title|replace("'","")}}')">
                <div class="poster">
                    <img src="{{m.poster}}" loading="lazy">
                    <div class="code">{{m.code}}</div>
                    <div class="playov"><i class="fas fa-play-circle fa-4x text-white"></i></div>
                </div>
                <div class="text-center mt-2 px-1">
                    <div class="fw-bold text-truncate">{{m.title}}</div>
                    <div class="d-flex justify-content-between align-items-center mt-1">
                        <small class="text-muted"><i class="fas fa-eye"></i> {{m.views|format_views}}</small>
                        <i onclick="toggleFav({{m.id}}, event)" class="fas fa-star {{'text-warning' if m.fav else 'text-secondary'}}" style="font-size:1.2rem;"></i>
                    </div>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<!-- SETTINGS MODAL -->
<div class="modal fade" id="settingsModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content bg-dark text-white border-orange">
            <div class="modal-header border-secondary">
                <h5 class="modal-title">{{ t('settings') }}</h5>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <form id="settingsForm">
                    <div class="mb-3">
                        <label class="form-label">{{ t('movie_path_label') }}</label>
                        <input type="text" class="form-control bg-black text-white border-secondary" name="movie_path" value="{{ movie_path }}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">{{ t('api_key_label') }}</label>
                        <input type="password" class="form-control bg-black text-white border-secondary" name="api_key" value="{{ api_key }}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">{{ t('lang_label') }}</label>
                        <select class="form-select bg-black text-white border-secondary" name="language">
                            <option value="tr" {{ 'selected' if lang == 'tr' else '' }}>Türkçe</option>
                            <option value="en" {{ 'selected' if lang == 'en' else '' }}>English</option>
                        </select>
                    </div>
                    <button type="button" class="btn btn-danger w-100" onclick="saveSettings()">{{ t('save') }}</button>
                </form>
            </div>
        </div>
    </div>
</div>

<!-- PLAYER MODAL -->
<div class="modal fade" id="playerModal" tabindex="-1" data-bs-backdrop="static">
    <div class="modal-dialog modal-dialog-centered modal-xl">
        <div class="modal-content bg-black border-0">
            <div class="modal-header border-0 py-1">
                <h6 class="modal-title text-white" id="ptitle"></h6>
                <button type="button" class="btn-close btn-close-white" onclick="closeModal()"></button>
            </div>
            <div class="modal-body p-0 position-relative">
                <video id="video" class="w-100" style="max-height:85vh;" controls autoplay playsinline></video>
                <button class="nav-btn-overlay prev-btn" onclick="playPrevious()"><i class="fas fa-backward"></i></button>
                <button class="nav-btn-overlay next-btn" onclick="randomPlay()"><i class="fas fa-forward"></i></button>
                <button class="player-chat-btn" onclick="toggleChat()"><i class="fas fa-comments"></i> Chat</button>
                <div id="autoNext" class="position-absolute top-50 start-50 translate-middle bg-dark px-4 py-3 rounded d-none text-center border border-orange">
                    <h5 class="text-white mb-3">{{ t('next_video') }}</h5>
                    <div class="display-4 text-danger fw-bold mb-3" id="nextSec">5</div>
                    <button class="btn btn-outline-light w-100" onclick="cancelAuto()">{{ t('cancel') }}</button>
                </div>
            </div>
        </div>
    </div>
</div>

<div id="miniPlayer" class="fixed-bottom d-none align-items-center px-3 shadow-lg">
    <div class="text-white fw-bold flex-grow-1 text-truncate" id="miniTitle">...</div>
    <button onclick="openModalAgain()" class="btn btn-sm btn-light me-2"><i class="fas fa-expand"></i></button>
    <button onclick="closeMini()" class="btn btn-sm btn-danger"><i class="fas fa-times"></i></button>
</div>

<div class="chat-window" id="chatWindow">
    <div class="bg-black p-2 border-bottom border-danger d-flex justify-content-between text-danger fw-bold">
        <span>😈 Partner</span><span style="cursor:pointer" onclick="toggleChat()">X</span>
    </div>
    <div id="chatBody" class="p-3 text-white" style="height:300px; overflow-y:auto;">
        <div class="bg-dark p-2 rounded mb-2">{{ t('partner_hello') }}</div>
    </div>
    <div class="p-2 bg-black d-flex gap-2">
        <input id="chatIn" class="form-control form-control-sm bg-dark text-white border-0" placeholder="{{ t('write_here') }}">
        <button onclick="askAI()" class="btn btn-sm btn-danger"><i class="fas fa-paper-plane"></i></button>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
let autoTimer, checkInterval;
let videoHistory = [];
let currentVideoTitle = "";
const modalEl = document.getElementById('playerModal');
const modal = new bootstrap.Modal(modalEl, {backdrop: 'static', keyboard: false, focus: false});
const video = document.getElementById('video');

function openPlayer(id, title, isBack=false){
    if(!isBack && (videoHistory.length === 0 || videoHistory[videoHistory.length-1].id !== id)) {
        videoHistory.push({id: id, title: title});
    }
    cancelAuto();
    currentVideoTitle = title;
    fetch(`/view/${id}`);
    document.getElementById('ptitle').innerText = title;
    document.getElementById('miniTitle').innerText = title;
    video.src = `/stream_transcode/${id}`;
    video.load();
    video.play().catch(e => console.log("Play failed:", e));
    modal.show();
    startEndChecker();
}

function playPrevious(){
    if(videoHistory.length > 1){
        videoHistory.pop();
        const prev = videoHistory[videoHistory.length - 1];
        openPlayer(prev.id, prev.title, true); 
    }
}

function startEndChecker() {
    if(checkInterval) clearInterval(checkInterval);
    let lastTime = -1;
    let stuckCount = 0;
    checkInterval = setInterval(() => {
        if (video.ended) { triggerAutoNext(); return; }
        if (video.readyState === 4 && video.networkState === 1 && !video.paused) {
            if (Math.abs(video.currentTime - lastTime) < 0.1) {
                stuckCount++;
                if (stuckCount > 3) triggerAutoNext();
            } else { stuckCount = 0; }
            lastTime = video.currentTime;
        }
    }, 1000);
}

function triggerAutoNext() {
    if(checkInterval) clearInterval(checkInterval);
    document.getElementById('autoNext').classList.remove('d-none');
    let s = 5;
    document.getElementById('nextSec').innerText = s;
    autoTimer = setInterval(() => {
        s--;
        document.getElementById('nextSec').innerText = s;
        if(s <= 0){ clearInterval(autoTimer); randomPlay(); }
    }, 1000);
}

function cancelAuto(){
    clearInterval(autoTimer);
    if(checkInterval) clearInterval(checkInterval);
    document.getElementById('autoNext').classList.add('d-none');
}

function randomPlay(){
    cancelAuto();
    fetch('/shuffle_data').then(r=>r.json()).then(d => {
        if(d.id !== undefined) openPlayer(d.id, d.title);
    });
}

function closeModal(){
    cancelAuto(); modal.hide();
    document.getElementById('miniPlayer').classList.remove('d-none');
    document.getElementById('miniPlayer').classList.add('d-flex');
}

function openModalAgain(){
    modal.show();
    document.getElementById('miniPlayer').classList.add('d-none');
    document.getElementById('miniPlayer').classList.remove('d-flex');
}

function closeMini(){
    video.pause(); video.src = ""; cancelAuto();
    document.getElementById('miniPlayer').classList.add('d-none');
    document.getElementById('miniPlayer').classList.remove('d-flex');
}

function search(val){
    val = val.toLowerCase();
    document.querySelectorAll('.item').forEach(el => {
        el.style.display = el.dataset.title.includes(val) ? '' : 'none';
    });
}

function filterTag(tag){
    document.querySelectorAll('.tag-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.item').forEach(el => {
        el.style.display = (tag === '' || el.dataset.tags.includes(tag.toLowerCase())) ? '' : 'none';
    });
}

function toggleFav(id, e){
    e.stopPropagation();
    fetch(`/fav/${id}`).then(r=>r.json()).then(d=>{
        e.target.className = d.fav ? 'fas fa-star text-warning' : 'fas fa-star text-secondary';
    });
}

function toggleLights(){ document.body.classList.toggle('lights-off'); }

function toggleChat(){
    const c = document.getElementById('chatWindow');
    c.style.display = c.style.display === 'flex' ? 'none' : 'flex';
}

function saveSettings() {
    const formData = new FormData(document.getElementById('settingsForm'));
    const data = {};
    formData.forEach((value, key) => data[key] = value);
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }).then(r => r.json()).then(d => {
        if(d.status === 'ok') location.reload();
    });
}

async function askAI(){
    const inp = document.getElementById('chatIn');
    const body = document.getElementById('chatBody');
    const q = inp.value; if(!q) return;
    body.innerHTML += `<div class="bg-danger p-2 rounded mb-2 ms-auto text-end" style="width:80%">${q}</div>`;
    inp.value = ''; body.scrollTop = body.scrollHeight;
    const contextQuery = currentVideoTitle ? `(Watching: ${currentVideoTitle}) ${q}` : q;
    try {
        const res = await fetch('/ask_ai', { 
            method:'POST', 
            headers:{'Content-Type':'application/x-www-form-urlencoded'}, 
            body: `query=${encodeURIComponent(contextQuery)}` 
        });
        const d = await res.json();
        body.innerHTML += `<div class="bg-dark p-2 rounded mb-2" style="width:80%">${d.answer}</div>`;
        body.scrollTop = body.scrollHeight;
    } catch(e){}
}

const hammertime = new Hammer(document.body);
hammertime.on('swipeleft', () => { randomPlay(); });
hammertime.on('swiperight', () => { playPrevious(); });
</script>
</body>
</html>
"""

# ====================== ROTALAR ======================
@app.route('/thumbnails/<f>')
def thumb(f): return send_from_directory(THUMB_FOLDER, f)

@app.route('/')
def index():
    scan_directory()
    return render_template_string(
        HTML_TEMPLATE, 
        movies=movies, 
        all_tags=all_tags, 
        t=T, 
        lang=current_settings["language"],
        movie_path=current_settings["movie_path"],
        api_key=current_settings["api_key"]
    )

@app.route('/fav')
def fav_page():
    scan_directory()
    fav_movies = [m for m in movies if m['fav']]
    return render_template_string(
        HTML_TEMPLATE, 
        movies=fav_movies, 
        all_tags=all_tags, 
        t=T, 
        lang=current_settings["language"],
        movie_path=current_settings["movie_path"],
        api_key=current_settings["api_key"]
    )

@app.route('/api/settings', methods=['POST'])
def update_settings():
    global current_settings
    data = request.json
    current_settings.update(data)
    save_settings(current_settings)
    init_ai()
    return jsonify({"status": "ok"})

@app.route('/fav/<int:vid>')
def toggle_fav_route(vid):
    vid = str(vid)
    is_fav = False
    if vid in favorites: favorites.remove(vid)
    else: favorites.append(vid); is_fav = True
    save_json(FAV_FILE, favorites)
    return jsonify({"fav": is_fav})

@app.route('/view/<int:vid>')
def view_movie(vid):
    vid = str(vid)
    views[vid] = views.get(vid, 0) + 1
    save_json(VIEWS_FILE, views)
    return "ok"

@app.route('/shuffle_data')
def shuffle_data():
    if movies:
        m = random.choice(movies)
        return jsonify({'id': m['id'], 'title': m['title']})
    return jsonify({'error': 'No video'}), 404

@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    q = request.form.get('query')
    if not ai_client: return jsonify({'answer': "Bağlantı yok."})
    video_list = ", ".join([m['title'] for m in random.sample(movies, min(10, len(movies)))]) if movies else ""
    system_prompt = f"You are MediaPulse assistant. Character: Flirty, naughty, uncensored, dirty talk. Address user as 'master' or 'handsome'. Archive has: {video_list}. Comment on what user is watching if available."
    try:
        comp = ai_client.chat.completions.create(
            model="grok-3",
            messages=[{"role":"system","content":system_prompt},{"role":"user","content":q}]
        )
        return jsonify({'answer': comp.choices[0].message.content})
    except: return jsonify({'answer': "Hata oluştu 🔥"})

@app.route('/stream_transcode/<int:vid>')
def stream_transcode(vid):
    m = next((x for x in movies if x['id'] == vid), None)
    if not m: return "Not found", 404
    path = m['path']
    if path.lower().endswith('.mp4'): return send_file(path)
    if not shutil.which("ffmpeg"): return "FFmpeg Missing", 500
    cmd = ['ffmpeg', '-i', path, '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', '-movflags', 'frag_keyframe+empty_moov+default_base_moof', '-f', 'mp4', 'pipe:1']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)
    return Response(proc.stdout, mimetype='video/mp4')

import webbrowser

def launch_ui():
    time.sleep(1.5)
    url = "http://localhost:5000"
    
    # Try Chrome App Mode first (more premium)
    browsers = []
    if os.name == 'nt': # Windows
        chrome_paths = [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe")
        ]
        browsers = [(p, f'"{p}" --app={url}') for p in chrome_paths if os.path.exists(p)]
    else: # Linux
        chrome_cmd = shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium")
        if chrome_cmd:
            browsers = [(chrome_cmd, f'{chrome_cmd} --app={url} --window-size=1280,720')]

    success = False
    for _, cmd in browsers:
        try:
            subprocess.Popen(cmd, shell=True)
            success = True
            break
        except: continue
        
    if not success:
        webbrowser.open(url)

if __name__ == '__main__':
    scan_directory()
    threading.Thread(target=launch_ui, daemon=True).start()
    print(f"🚀 MediaPulse Running -> http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
