#!/usr/bin/env python3
"""
YuvinaLoad – Local Download Server
Serves the frontend and downloads YouTube videos via yt-dlp.
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
COOKIES_PATH    = None
COOKIES_BROWSER = None

def get_cookies_args():
    if COOKIES_PATH:
        return ['--cookies', COOKIES_PATH]
    elif COOKIES_BROWSER:
        return ['--cookies-from-browser', COOKIES_BROWSER]
    return []



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


# ── Check if ffmpeg is available ───────────────────────
def check_ffmpeg_available():
    # 1. Check in PATH first
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    # 2. Check if local ffmpeg.exe exists in project root
    local_ffmpeg = os.path.join(WEBROOT, 'ffmpeg.exe')
    if os.path.exists(local_ffmpeg):
        return True
    return False


# ── Download FFmpeg automatically if missing ───────────
def download_ffmpeg():
    import urllib.request
    import zipfile
    import io
    
    url = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-win-64.zip"
    print('\n ╔════════════════════════════════════════════════════════╗')
    print(' ║  FFmpeg is required for 1080p/4K merging & MP3 audio.  ║')
    print(' ║  Downloading lightweight FFmpeg build (~18MB)...      ║')
    print(' ╚════════════════════════════════════════════════════════╝\n')
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            zip_data = response.read()
        
        print("  [FFmpeg] Extracting ffmpeg.exe...")
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            z.extract("ffmpeg.exe", WEBROOT)
        print("  [FFmpeg] ✅ FFmpeg installed successfully in project directory!\n")
        return True
    except Exception as e:
        print(f"  [FFmpeg] ❌ Auto-install failed: {e}")
        print("           Please download FFmpeg manually or try again.\n")
        return False


# ── Quality string → yt-dlp format ────────────────────
def build_format(format_type, quality_str, ffmpeg_available=True):
    if format_type == 'mp3':
        kbps  = int(re.search(r'\d+', quality_str).group()) if re.search(r'\d+', quality_str) else 128
        aq    = {320: '0', 256: '2', 192: '4', 128: '5'}.get(kbps, '5')
        return 'bestaudio/best', ['-x', '--audio-format', 'mp3', '--audio-quality', aq]

    m   = re.search(r'(\d+)p', quality_str)
    res = m.group(1) if m else '720'

    if not ffmpeg_available:
        # Without FFmpeg, we MUST download a pre-merged format (no + sign) to get both audio and video
        if format_type == 'webm':
            return f'best[height<={res}][ext=webm]/best[height<={res}]/best', []
        # mp4
        return f'best[height<={res}][ext=mp4]/best[height<={res}]/best', []

    if format_type == 'webm':
        fmt = (f'bestvideo[height<={res}][ext=webm]+bestaudio[ext=webm]'
               f'/bestvideo[height<={res}]+bestaudio/best[height<={res}]')
        return fmt, ['--merge-output-format', 'webm']

    # mp4 (default with FFmpeg)
    fmt = (f'bestvideo[height<={res}][ext=mp4]+bestaudio[ext=m4a]'
           f'/bestvideo[height<={res}]+bestaudio/best[height<={res}]/best')
    return fmt, ['--merge-output-format', 'mp4']


# ── MIME helper ─────────────────────────────────────────
def mime_for(fmt):
    return {'mp3': 'audio/mpeg', 'webm': 'video/webm'}.get(fmt, 'video/mp4')


# ── Background download task executor ───────────────────
def run_download_task(task_id, vid, fmt, quality):
    task = DOWNLOAD_TASKS[task_id]
    task["status"] = "downloading"
    task["phase"] = "Initializing download..."

    ffmpeg_available = check_ffmpeg_available()
    yt_fmt, extra = build_format(fmt, quality, ffmpeg_available)

    if fmt == 'mp3' and not ffmpeg_available:
        task["status"] = "failed"
        task["error"] = "FFmpeg is required to extract MP3 audio. Please download FFmpeg and add it to your PATH, or choose a video format instead."
        return

    if not ffmpeg_available and fmt in ['mp4', 'webm']:
        task["phase"] = "FFmpeg not found. Downloading pre-merged video (max 720p)..."

    # Create temporary directory
    tmpdir_obj = tempfile.TemporaryDirectory()
    task["temp_dir_obj"] = tmpdir_obj
    tmpdir = tmpdir_obj.name

    cookies_args = get_cookies_args()
    out_tmpl = os.path.join(tmpdir, 'YuvinaLoad_%(title)s.%(ext)s')
    cmd = YTDLP + cookies_args + [
        '--no-config',
        '-f', yt_fmt,
        '-o', out_tmpl,
        '--no-playlist',
        '--restrict-filenames',
    ] + extra + [f'https://www.youtube.com/watch?v={vid}']

    print(f'  ⬇  [Task {task_id[:8]}] Downloading {vid} [{fmt} {quality}]')
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors='replace'
        )

        current_stream = "file"
        bot_blocked = False
        for line in p.stdout:
            line = line.strip()
            if not line:
                continue

            print(f'  [{task_id[:8]}] {line}') # Log to server console

            if "Sign in" in line or "confirm you're not a bot" in line:
                bot_blocked = True

            if line.startswith('[download]'):
                if 'Destination:' in line:
                    dest = line.split('Destination:')[1].strip()
                    ext = dest.split('.')[-1].lower() if '.' in dest else ''
                    if ext in ['mp4', 'webm', 'mkv', 'avi']:
                        current_stream = "video"
                    elif ext in ['m4a', 'mp3', 'opus', 'ogg', 'wav']:
                        current_stream = "audio"
                    else:
                        current_stream = "file"
                    task["phase"] = f"Downloading {current_stream} stream..."
                
                # Check progress stats
                m = re.search(r'(\d+\.\d+)%\s+of\s+(\S+)\s+at\s+(\S+)\s+ETA\s+(\S+)', line)
                if m:
                    task["progress"] = float(m.group(1))
                    task["speed"] = m.group(3)
                    task["eta"] = m.group(4)
                    task["phase"] = f"Downloading {current_stream} stream ({task['progress']}%)"
            elif line.startswith('[Merger]'):
                task["phase"] = "Merging video and audio streams (using FFmpeg)..."
                task["progress"] = 92.0
            elif line.startswith('[ExtractAudio]'):
                task["phase"] = "Extracting MP3 audio (using FFmpeg)..."
                task["progress"] = 94.0
            elif line.startswith('[ffmpeg]'):
                task["phase"] = "Processing output format (using FFmpeg)..."
                task["progress"] = 97.0

        p.wait()

        if p.returncode != 0:
            task["status"] = "failed"
            if bot_blocked:
                task["error"] = ("YouTube blocked this request (Bot detection).<br><br>"
                                 "<b>To fix this:</b><br>"
                                 "• <b>For local runs</b>: Set <code>YOUTUBE_COOKIES_BROWSER=chrome</code> (or edge, firefox) in <code>start.bat</code> and restart.<br>"
                                 "• <b>For live deployments (Render, Railway, etc.)</b>: Export YouTube cookies using a browser extension (like 'Get cookies.txt LOCALLY'), copy the file contents, and add it as the <code>YOUTUBE_COOKIES</code> environment variable in your dashboard settings.")
            else:
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


# ══════════════════════════════════════════════════════
#  Request Handler
# ══════════════════════════════════════════════════════
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
        else:                                       super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin',  '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.end_headers()

    # ── /api/info ─────────────────────────────────────
    def api_info(self, params):
        vid = params.get('id', '')
        if not vid:
            self.json({'error': 'Missing ?id='}, 400); return
        if not YTDLP:
            self.json({'error': 'yt-dlp not found'}, 500); return

        try:
            cookies_args = get_cookies_args()
            r = subprocess.run(
                YTDLP + cookies_args + ['--no-config', '-f', 'best', '--dump-json', '--no-playlist', '--skip-download',
                          f'https://www.youtube.com/watch?v={vid}'],
                capture_output=True, text=True, timeout=40
            )
            if r.returncode != 0:
                print(f"[YuvinaLoad Error] yt-dlp stderr: {r.stderr}")
                err_msg = "Video unavailable, private, or blocked by YouTube"
                if "429" in r.stderr or "Too Many Requests" in r.stderr:
                    err_msg = "YouTube rate-limited this server IP (HTTP 429)"
                elif "Sign in" in r.stderr or "confirm you're not a bot" in r.stderr:
                    err_msg = ("YouTube blocked this request (Bot detection).<br><br>"
                               "<b>To fix this:</b><br>"
                               "• <b>For local runs</b>: Set <code>YOUTUBE_COOKIES_BROWSER=chrome</code> (or edge, firefox) in <code>start.bat</code> and restart.<br>"
                               "• <b>For live deployments (Render, Railway, etc.)</b>: Export YouTube cookies using a browser extension (like 'Get cookies.txt LOCALLY'), copy the file contents, and add it as the <code>YOUTUBE_COOKIES</code> environment variable in your dashboard settings.")
                
                details = r.stderr.strip().split('\n')[-1] if r.stderr else "Unknown error"
                self.json({'error': f"{err_msg}. Details: {details}"}, 404); return

            d = json.loads(r.stdout)
            self.json({
                'title':      d.get('title',      'Unknown'),
                'channel':    d.get('uploader',   'Unknown'),
                'duration':   d.get('duration',   0),
                'thumbnail':  d.get('thumbnail',  ''),
                'view_count': d.get('view_count', 0),
            })
        except subprocess.TimeoutExpired:
            self.json({'error': 'Timed out fetching info'}, 504)
        except Exception as e:
            self.json({'error': str(e)}, 500)

    # ── /api/download ─────────────────────────────────
    def api_download(self, params):
        vid      = params.get('id',      '')
        fmt      = params.get('format',  'mp4')
        quality  = params.get('quality', '720p')

        if not vid:
            self.json({'error': 'Missing ?id='}, 400); return
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
        t = threading.Thread(target=run_download_task, args=(task_id, vid, fmt, quality))
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


# ══════════════════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════════════════
def main():
    global YTDLP, COOKIES_PATH, COOKIES_BROWSER

    # Load cookies from environment variables or local file
    env_cookies = os.environ.get('YOUTUBE_COOKIES')
    if env_cookies:
        try:
            # Normalize escape sequences if pasted as a single line in environment dashboard
            if '\\n' in env_cookies:
                env_cookies = env_cookies.replace('\\n', '\n')
            if '\\t' in env_cookies:
                env_cookies = env_cookies.replace('\\t', '\t')

            # Write environment cookies to a temporary file
            temp_cookies = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
            temp_cookies.write(env_cookies)
            temp_cookies.close()
            COOKIES_PATH = temp_cookies.name
            print(f"  [Cookies] Loaded cookies from YOUTUBE_COOKIES environment variable!")
            
            # Clean up temp file on shutdown
            import atexit
            def cleanup_cookies():
                if os.path.exists(temp_cookies.name):
                    try: os.remove(temp_cookies.name)
                    except: pass
            atexit.register(cleanup_cookies)
        except Exception as e:
            print(f"  [Cookies] ❌ Failed to write YOUTUBE_COOKIES: {e}")
    else:
        local_cookies = os.path.join(WEBROOT, 'cookies.txt')
        if os.path.exists(local_cookies):
            COOKIES_PATH = local_cookies
            print("  [Cookies] Loaded cookies from local cookies.txt file!")
        else:
            env_cookies_browser = os.environ.get('YOUTUBE_COOKIES_BROWSER')
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

    # Add project directory to PATH so local ffmpeg.exe can be discovered by yt-dlp
    if WEBROOT not in os.environ['PATH']:
        os.environ['PATH'] = WEBROOT + os.pathsep + os.environ['PATH']

    print('\n ╔════════════════════════════════════════╗')
    print(' ║   YuvinaLoad  –  Local Download Server  ║')
    print(' ╚════════════════════════════════════════╝\n')

    # Automatically check and download FFmpeg if running on Windows and missing
    if sys.platform.startswith('win') and not check_ffmpeg_available():
        download_ffmpeg()

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
