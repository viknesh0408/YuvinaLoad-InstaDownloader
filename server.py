#!/usr/bin/env python3
"""
YuvinaLoad – Local Download Server
Serves the frontend and downloads Instagram media via yt-dlp.
Run via start.bat or:  python server.py
"""

import http.server
import socketserver
import subprocess
import json
import os
import sys
import re
import urllib.parse
import tempfile
import threading
import webbrowser
import uuid
import time

PORT    = int(os.environ.get('PORT', 8080))
WEBROOT = os.path.dirname(os.path.abspath(__file__))
YTDLP   = None   # resolved at startup

# Global dictionary to hold active and completed download tasks
DOWNLOAD_TASKS  = {}
COOKIES_BROWSER        = None
INSTAGRAM_COOKIES_PATH = None

def get_target_url(params):
    url_param = params.get('url', '')
    return url_param.strip()

def normalize_cookies(raw_content):
    raw_content = raw_content.strip()
    if not raw_content:
        return ""

    # Case 1: Netscape cookie format
    if raw_content.startswith("# Netscape") or raw_content.startswith("# HTTP Cookie") or ".instagram.com" in raw_content or "instagram.com" in raw_content:
        lines = []
        raw_lines = []
        if "\n" in raw_content:
            raw_lines = raw_content.split("\n")
        else:
            # Single collapsed line (spaces instead of newlines)
            tokens = raw_content.split()
            if tokens and tokens[0] == "#":
                while tokens and (tokens[0].startswith("#") or tokens[0] in ["Netscape", "HTTP", "Cookie", "File"]):
                    tokens.pop(0)
            for i in range(0, len(tokens) - 6, 7):
                t = tokens[i:i+7]
                if t[1].upper() in ["TRUE", "FALSE"] and t[3].upper() in ["TRUE", "FALSE"]:
                    lines.append("\t".join(t))
            if lines:
                return "# Netscape HTTP Cookie File\n" + "\n".join(lines) + "\n"

        if raw_lines:
            parsed_lines = ["# Netscape HTTP Cookie File"]
            for line in raw_lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = re.split(r'\t+|\s{2,}', line)
                if len(parts) < 7:
                    parts = line.split()
                if len(parts) >= 7:
                    domain = parts[0]
                    sub = parts[1]
                    path = parts[2]
                    secure = parts[3]
                    exp = parts[4]
                    name = parts[5]
                    value = " ".join(parts[6:])
                    if sub.upper() in ["TRUE", "FALSE"] and secure.upper() in ["TRUE", "FALSE"]:
                        parsed_lines.append(f"{domain}\t{sub.upper()}\t{path}\t{secure.upper()}\t{exp}\t{name}\t{value}")
            if len(parsed_lines) > 1:
                return "\n".join(parsed_lines) + "\n"

    # Case 2: JSON format
    try:
        data = json.loads(raw_content)
        lines = ["# Netscape HTTP Cookie File"]
        default_exp = str(int(time.time()) + 31536000) # 1 year expiry
        
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                value = item.get("value")
                if not name or value is None:
                    continue
                domain = item.get("domain", ".instagram.com")
                path = item.get("path", "/")
                secure = "TRUE" if item.get("secure", True) else "FALSE"
                exp = item.get("expirationDate") or item.get("expiry") or default_exp
                exp = str(int(exp))
                sub = "TRUE" if domain.startswith(".") else "FALSE"
                lines.append(f"{domain}\t{sub}\t{path}\t{secure}\t{exp}\t{name}\t{value}")
            return "\n".join(lines) + "\n"
        
        elif isinstance(data, dict):
            for name, value in data.items():
                if name and value is not None:
                    lines.append(f".instagram.com\tTRUE\t/\tTRUE\t{default_exp}\t{name}\t{value}")
            return "\n".join(lines) + "\n"
    except Exception:
        pass

    # Case 3: Raw cookie header string (e.g. "sessionid=abc; rur=def;") or standard HTTP Header
    header_content = raw_content
    if header_content.lower().startswith("cookie:"):
        header_content = header_content[7:].strip()
    
    if "=" in header_content:
        pairs = header_content.split(";")
        lines = ["# Netscape HTTP Cookie File"]
        default_exp = str(int(time.time()) + 31536000)
        has_valid_pair = False
        for pair in pairs:
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            parts = pair.split("=", 1)
            name = parts[0].strip()
            value = parts[1].strip()
            if name and value:
                lines.append(f".instagram.com\tTRUE\t/\tTRUE\t{default_exp}\t{name}\t{value}")
                has_valid_pair = True
        if has_valid_pair:
            return "\n".join(lines) + "\n"

    # Fallback: Just return it as-is
    return raw_content

def get_cookies_args(url=""):
    if INSTAGRAM_COOKIES_PATH:
        return ['--cookies', INSTAGRAM_COOKIES_PATH]
    elif COOKIES_BROWSER:
        return ['--cookies-from-browser', COOKIES_BROWSER]
    return []

def build_ytdlp_base_args(url=""):
    """Return common yt-dlp anti-bot and compatibility flags."""
    return [
        '--no-check-certificates',
        '--add-header', 'Accept-Language:en-US,en;q=0.9',
        '--socket-timeout', '30',
    ]

# ── Locate yt-dlp ──────────────────────────────────────
def find_ytdlp():
    for cmd in ['yt-dlp', 'yt_dlp']:
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=True)
            return [cmd]
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    try:
        subprocess.run([sys.executable, '-m', 'yt_dlp', '--version'],
                       capture_output=True, check=True)
        return [sys.executable, '-m', 'yt_dlp']
    except Exception:
        return None

# ── MIME helper ─────────────────────────────────────────
def mime_for(fmt):
    return {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}.get(fmt, 'video/mp4')

# ── Background download task executor ───────────────────
def run_download_task(task_id, url, fmt, quality):
    task = DOWNLOAD_TASKS[task_id]
    task["status"] = "downloading"
    task["phase"] = "Initializing download..."

    if fmt == 'jpg':
        task["phase"] = "Downloading image..."
        task["progress"] = 10.0
        
        # Create temporary directory
        tmpdir_obj = tempfile.TemporaryDirectory()
        task["temp_dir_obj"] = tmpdir_obj
        tmpdir = tmpdir_obj.name
        
        try:
            import urllib.request
            img_url = None
            shortcode = None
            
            shortcode_match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
            shortcode = shortcode_match.group(1) if shortcode_match else None
            if shortcode:
                redirect_url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
                req = urllib.request.Request(
                    redirect_url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    img_url = response.geturl()

            if not img_url:
                img_url = url

            req = urllib.request.Request(
                img_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            )
            
            out_filename = "instagram_image.jpg"
            if shortcode:
                out_filename = f"instagram_{shortcode}.jpg"
            
            out_path = os.path.join(tmpdir, out_filename)
            
            task["progress"] = 50.0
            with urllib.request.urlopen(req, timeout=15) as response:
                with open(out_path, 'wb') as out_file:
                    out_file.write(response.read())
            
            task["status"] = "completed"
            task["progress"] = 100.0
            task["filename"] = out_filename
            task["filepath"] = out_path
            task["phase"] = "Download finished on server!"
            
        except Exception as e:
            task["status"] = "failed"
            task["error"] = f"Failed to download image: {str(e)}"
            tmpdir_obj.cleanup()
            return

        print(f"  [Task {task_id[:8]}] Image download completed: {out_filename}")
        return

    # Create temporary directory
    tmpdir_obj = tempfile.TemporaryDirectory()
    task["temp_dir_obj"] = tmpdir_obj
    tmpdir = tmpdir_obj.name

    cookies_args = get_cookies_args(url)
    out_tmpl = os.path.join(tmpdir, 'YuvinaLoad_%(title)s.%(ext)s')
    cmd = YTDLP + cookies_args + build_ytdlp_base_args(url) + [
        '--no-config',
        '-f', 'best',
        '-o', out_tmpl,
        '--no-playlist',
        '--restrict-filenames',
    ] + [url]

    print(f'  ⬇  [Task {task_id[:8]}] Downloading {url} [{fmt} {quality}]')
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors='replace'
        )

        for line in p.stdout:
            line = line.strip()
            if not line:
                continue

            print(f'  [{task_id[:8]}] {line}') # Log to server console

            if line.startswith('[download]'):
                if 'Destination:' in line:
                    task["phase"] = "Downloading video stream..."
                
                # Check progress stats
                m = re.search(r'(\d+\.\d+)%\s+of\s+(\S+)\s+at\s+(\S+)\s+ETA\s+(\S+)', line)
                if m:
                    task["progress"] = float(m.group(1))
                    task["speed"] = m.group(3)
                    task["eta"] = m.group(4)
                    task["phase"] = f"Downloading video stream ({task['progress']}%)"

        p.wait()

        if p.returncode != 0:
            task["status"] = "failed"
            task["error"] = f"yt-dlp failed (code {p.returncode}). Video might be private, blocked, or unavailable."
            tmpdir_obj.cleanup()
            return

        files = os.listdir(tmpdir)
        if not files:
            task["status"] = "failed"
            task["error"] = "No output file was created."
            tmpdir_obj.cleanup()
            return

        # Success!
        task["status"] = "completed"
        task["progress"] = 100.0
        task["filename"] = files[0]
        task["filepath"] = os.path.join(tmpdir, files[0])
        task["phase"] = "Download finished on server!"
        print(f"  ✅ [Task {task_id[:8]}] Completed: {files[0]}")

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        if tmpdir_obj:
            try:
                tmpdir_obj.cleanup()
            except Exception:
                pass


# ══════════════════════════════
#  Request Handler
# ══════════════════════════════
class YuvinaHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBROOT, **kwargs)

    # Silence default access logs
    def log_message(self, *args): pass

    # Enable browser caching for static files to optimize page loads
    def end_headers(self):
        path = self.translate_path(self.path)
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.ico', '.woff', '.woff2']:
            self.send_header('Cache-Control', 'public, max-age=86400')
        super().end_headers()

    # ── JSON response helper ──────────────────────────
    def json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',  'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    # ── Route GET requests ────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))

        if   parsed.path == '/api/info':            self.api_info(params)
        elif parsed.path == '/api/download':        self.api_download(params)
        elif parsed.path == '/api/download/status': self.api_download_status(params)
        elif parsed.path == '/api/download/file':   self.api_download_file(params)
        elif parsed.path == '/api/health':          self.api_health()
        else:                                       super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin',  '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.end_headers()

    # ── /api/health ────────────────────────────────────
    def api_health(self):
        is_cloud = bool(os.environ.get('PORT'))  # Render/Railway set PORT env var
        
        insta_cookie_status = 'none'
        if INSTAGRAM_COOKIES_PATH: insta_cookie_status = 'cookies_file'
        elif COOKIES_BROWSER:      insta_cookie_status = f'browser:{COOKIES_BROWSER}'
        
        self.json({
            'status':            'ok',
            'ytdlp':             bool(YTDLP),
            'cookies_instagram': insta_cookie_status,
            'cloud_mode':        is_cloud,
        })

    # ── /api/info ─────────────────────────────────────
    def api_info(self, params):
        url = get_target_url(params)
        if not url:
            self.json({'error': 'Missing ?url='}, 400); return
        if not YTDLP:
            self.json({'error': 'yt-dlp not found'}, 500); return

        try:
            cookies_args = get_cookies_args(url)
            r = subprocess.run(
                YTDLP + cookies_args + build_ytdlp_base_args(url) + [
                    '--no-config', '--dump-json', '--no-playlist', '--skip-download',
                    url,
                ],
                capture_output=True, text=True, timeout=45
            )
            if r.returncode != 0:
                print(f"[YuvinaLoad Error] yt-dlp stderr: {r.stderr}")
                
                # Check for Instagram photo post fallback
                try:
                    import urllib.request
                    shortcode_match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
                    shortcode = shortcode_match.group(1) if shortcode_match else "media"
                    
                    redirect_url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
                    req = urllib.request.Request(
                        redirect_url, 
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                    )
                    with urllib.request.urlopen(req, timeout=15) as response:
                        direct_img_url = response.geturl()
                    
                    self.json({
                        'title':      f"Instagram Photo Post ({shortcode})",
                        'channel':    "Instagram Post",
                        'duration':   0,
                        'thumbnail':  direct_img_url,
                        'view_count': 0,
                        'type':       'image',
                    })
                    return
                except Exception as fallback_err:
                    print(f"[YuvinaLoad Warning] Instagram photo fallback failed: {fallback_err}")

                err_msg = "Media unavailable, private, or blocked by platform"
                if "429" in r.stderr or "Too Many Requests" in r.stderr:
                    err_msg = "Rate-limited by platform (HTTP 429)"
                
                details = r.stderr.strip().split('\n')[-1] if r.stderr else "Unknown error"
                self.json({'error': f"{err_msg}. Details: {details}"}, 404); return

            d = json.loads(r.stdout)
            media_type = 'video'
            ext = d.get('ext', '').lower()
            if ext in ['jpg', 'jpeg', 'png', 'webp'] or (d.get('vcodec') == 'none' and d.get('acodec') == 'none'):
                media_type = 'image'

            self.json({
                'title':      d.get('title',      'Unknown'),
                'channel':    d.get('uploader',   'Unknown'),
                'duration':   d.get('duration',   0),
                'thumbnail':  d.get('thumbnail',  ''),
                'view_count': d.get('view_count', 0),
                'type':       media_type,
            })
        except subprocess.TimeoutExpired:
            self.json({'error': 'Timed out fetching info'}, 504)
        except Exception as e:
            self.json({'error': str(e)}, 500)

    # ── /api/download ─────────────────────────────────
    def api_download(self, params):
        url = get_target_url(params)
        fmt      = params.get('format',  'mp4')
        quality  = params.get('quality', 'Best Quality (Original)')

        if not url:
            self.json({'error': 'Missing ?url='}, 400); return
        if not YTDLP:
            self.json({'error': 'yt-dlp not installed. Please restart via start.bat'}, 500); return

        # Periodic memory/disk cleanup of tasks older than 30 mins (1800 seconds)
        now = time.time()
        to_delete = []
        for tid, tinfo in list(DOWNLOAD_TASKS.items()):
            if now - tinfo.get('created_at', now) > 1800:
                to_delete.append(tid)
        for tid in to_delete:
            tinfo = DOWNLOAD_TASKS.pop(tid, None)
            if tinfo and tinfo.get('temp_dir_obj'):
                try:
                    tinfo['temp_dir_obj'].cleanup()
                except Exception:
                    pass

        # Register new task
        task_id = str(uuid.uuid4())
        DOWNLOAD_TASKS[task_id] = {
            "status": "pending",
            "progress": 0.0,
            "speed": "",
            "eta": "",
            "phase": "Queued on server...",
            "error": "",
            "filename": "",
            "filepath": "",
            "temp_dir_obj": None,
            "created_at": now
        }

        # Spawn background thread to run yt-dlp
        t = threading.Thread(target=run_download_task, args=(task_id, url, fmt, quality))
        t.daemon = True
        t.start()

        self.json({'task_id': task_id})

    # ── /api/download/status ──────────────────────────
    def api_download_status(self, params):
        task_id = params.get('task_id', '')
        if not task_id or task_id not in DOWNLOAD_TASKS:
            self.json({'error': 'Task not found'}, 404); return
        
        task = DOWNLOAD_TASKS[task_id]
        self.json({
            'status':   task['status'],
            'progress': task['progress'],
            'speed':    task['speed'],
            'eta':      task['eta'],
            'phase':    task['phase'],
            'error':    task['error'],
            'filename': task['filename']
        })

    # ── /api/download/file ────────────────────────────
    def api_download_file(self, params):
        task_id = params.get('task_id', '')
        if not task_id or task_id not in DOWNLOAD_TASKS:
            self.json({'error': 'Task not found'}, 404); return
        
        task = DOWNLOAD_TASKS[task_id]
        if task['status'] != 'completed':
            self.json({'error': 'Download is not ready'}, 400); return
        
        filepath = task['filepath']
        filename = task['filename']
        filesize = os.path.getsize(filepath)
        fmt = filename.split('.')[-1].lower() if '.' in filename else 'mp4'

        try:
            self.send_response(200)
            self.send_header('Content-Type',        mime_for(fmt))
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Length',      str(filesize))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk: break
                    self.wfile.write(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass # client aborted or finished
        finally:
            # Clean up temp folder and remove from dictionary
            if task['temp_dir_obj']:
                try:
                    task['temp_dir_obj'].cleanup()
                except Exception:
                    pass
            DOWNLOAD_TASKS.pop(task_id, None)


# ══════════════════════════════
#  Entry Point
# ══════════════════════════════
def main():
    global YTDLP, COOKIES_BROWSER, INSTAGRAM_COOKIES_PATH

    # Load Instagram cookies from environment variables or local file
    env_insta_cookies = os.environ.get('INSTAGRAM_COOKIES')
    if env_insta_cookies:
        try:
            if '\\n' in env_insta_cookies:
                env_insta_cookies = env_insta_cookies.replace('\\n', '\n')
            if '\\t' in env_insta_cookies:
                env_insta_cookies = env_insta_cookies.replace('\\t', '\t')

            normalized_insta = normalize_cookies(env_insta_cookies)
            temp_insta_cookies = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
            temp_insta_cookies.write(normalized_insta)
            temp_insta_cookies.close()
            INSTAGRAM_COOKIES_PATH = temp_insta_cookies.name
            print(f"  [Cookies] Loaded Instagram cookies from INSTAGRAM_COOKIES environment variable!")
            
            import atexit
            def cleanup_insta_cookies():
                if os.path.exists(temp_insta_cookies.name):
                    try: os.remove(temp_insta_cookies.name)
                    except: pass
            atexit.register(cleanup_insta_cookies)
        except Exception as e:
            print(f"  [Cookies] ❌ Failed to write INSTAGRAM_COOKIES: {e}")
    else:
        local_insta_cookies = os.path.join(WEBROOT, 'instagram_cookies.txt')
        if os.path.exists(local_insta_cookies):
            INSTAGRAM_COOKIES_PATH = local_insta_cookies
            print("  [Cookies] Loaded Instagram cookies from local instagram_cookies.txt file!")
        else:
            env_cookies_browser = os.environ.get('INSTAGRAM_COOKIES_BROWSER')
            if env_cookies_browser:
                COOKIES_BROWSER = env_cookies_browser.strip().lower()
                print(f"  [Cookies] Configured to use cookies from browser: {COOKIES_BROWSER}")

    # Reconfigure stdout/stderr to UTF-8 on Windows to prevent UnicodeEncodeError
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Add project directory and temp directory to PATH so local tools can be discovered
    temp_dir = tempfile.gettempdir()
    for d in [WEBROOT, temp_dir]:
        if d not in os.environ['PATH']:
            os.environ['PATH'] = d + os.pathsep + os.environ['PATH']

    print('\n ╔════════════════════════════════════════╗')
    print(' ║   YuvinaLoad – Instagram Downloader    ║')
    print(' ╚════════════════════════════════════════╝\n')

    # Proactively upgrade yt-dlp to latest version if running on Render/Railway/etc.
    if os.environ.get('PORT') or os.environ.get('RENDER') or os.environ.get('RAILWAY_STATIC_URL'):
        print(' ☁️  Cloud environment detected. Proactively upgrading yt-dlp to latest version...')
        try:
            # Run pip upgrade
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp'],
                capture_output=True, text=True, timeout=60
            )
            print(' ✅ yt-dlp upgraded successfully!')
        except Exception as e:
            print(f' ⚠  Failed to upgrade yt-dlp: {e}')

    YTDLP = find_ytdlp()

    if not YTDLP:
        print(' ⚠  yt-dlp not found. Installing now...')
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-q', '--upgrade', 'yt-dlp'],
            capture_output=False
        )
        YTDLP = find_ytdlp()
        if YTDLP:
            print(' ✅ yt-dlp installed!\n')
        else:
            print(' ❌ Auto-install failed.')
            print('    Please run manually:  pip install yt-dlp\n')

    print(f' 🌐  http://localhost:{PORT}')
    print(f' 📁  {WEBROOT}')
    print('\n Keep this window open. Press Ctrl+C to stop.\n')

    # Open browser locally, but skip in cloud/server environments
    if not os.environ.get('PORT'):
        threading.Timer(1.2, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()

    # Use ThreadingTCPServer to avoid blocking on concurrent connections
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('', PORT), YuvinaHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n\n Server stopped. Goodbye!')


if __name__ == '__main__':
    main()
