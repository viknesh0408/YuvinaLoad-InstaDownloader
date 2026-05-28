/* ══════════════════════════════════════════════
   YuvinaLoad – Main JavaScript
   ══════════════════════════════════════════════ */

'use strict';

// ══════════════════════════════
//  Detect if running via server
//  (localhost) or file://
// ══════════════════════════════
const IS_SERVER = ['http:', 'https:'].includes(location.protocol);

// ══════════════════════════════
//  DOM References
// ══════════════════════════════
const videoUrlInput   = document.getElementById('videoUrl');
const fetchBtn        = document.getElementById('fetchBtn');
const pasteBtn        = document.getElementById('pasteBtn');
const statusMsg       = document.getElementById('statusMsg');
const videoPreview    = document.getElementById('videoPreview');
const previewThumb    = document.getElementById('previewThumb');
const previewTitle    = document.getElementById('previewTitle');
const previewChannel  = document.getElementById('previewChannel');
const previewDuration = document.getElementById('previewDuration');
const previewViews    = document.getElementById('previewViews');
const qualityGrid     = document.getElementById('qualityGrid');
const downloadBtn     = document.getElementById('downloadBtn');
const dlProgressFill  = document.getElementById('dlProgressFill');
const dlProgressText  = document.getElementById('dlProgressText');
const dlModalSub      = document.getElementById('dlModalSub');

let selectedFormat  = 'mp4';
let selectedQuality = null;
let currentVideoId  = null;

// ══════════════════════════════
//  Show "Use start.bat" banner
//  when opened as a file://
// ══════════════════════════════
if (!IS_SERVER) {
  document.addEventListener('DOMContentLoaded', () => {
    const banner = document.createElement('div');
    banner.id = 'serverBanner';
    banner.innerHTML = `
      <div class="server-banner-inner">
        <div class="server-banner-icon"><i class="bi bi-exclamation-triangle-fill"></i></div>
        <div class="server-banner-text">
          <strong>Action Required:</strong> Open this site using
          <code>start.bat</code> (double-click it) instead of
          <code>index.html</code> for downloads to work.
        </div>
        <button class="server-banner-close" onclick="this.parentElement.parentElement.remove()">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
    `;
    document.body.insertAdjacentElement('afterbegin', banner);
  });

  // Inject banner styles
  const s = document.createElement('style');
  s.textContent = `
    #serverBanner {
      position: fixed; bottom: 0; left: 0; right: 0;
      background: linear-gradient(135deg, #ff2d55 0%, #a855f7 100%);
      color: #fff; z-index: 9999; font-size: .875rem;
    }
    .server-banner-inner {
      display: flex; align-items: center; gap: 12px;
      max-width: 900px; margin: 0 auto; padding: 12px 20px;
    }
    .server-banner-icon { font-size: 1.2rem; flex-shrink: 0; }
    .server-banner-text { flex: 1; }
    .server-banner-text code {
      background: rgba(255,255,255,0.2); border-radius: 4px; padding: 1px 6px;
    }
    .server-banner-close {
      background: rgba(255,255,255,0.2); border: none; color: #fff;
      border-radius: 50%; width: 28px; height: 28px; cursor: pointer;
      flex-shrink: 0; font-size: .9rem; display: flex; align-items: center;
      justify-content: center;
    }
    .server-banner-close:hover { background: rgba(255,255,255,0.35); }
  `;
  document.head.appendChild(s);
}

// ══════════════════════════════
//  Quality Options Per Format
// ══════════════════════════════
const qualityOptions = {
  mp4:  ['2160p (4K)', '1080p (FHD)', '720p (HD)', '480p', '360p', '144p'],
  mp3:  ['320 kbps', '256 kbps', '192 kbps', '128 kbps'],
  webm: ['1080p', '720p', '480p', '360p'],
};

// Navbar Scroll and Active state handled by unified scroll listener at the bottom.

// ══════════════════════════════
//  Animated Stat Counters
// ══════════════════════════════
function animateCounters() {
  document.querySelectorAll('.stat-num').forEach(el => {
    const target = +el.dataset.target;
    const step   = target / (1800 / 16);
    let cur = 0;
    const t = setInterval(() => {
      cur += step;
      if (cur >= target) { cur = target; clearInterval(t); }
      el.textContent = Math.floor(cur);
    }, 16);
  });
}
const statsObs = new IntersectionObserver(entries => {
  if (entries[0].isIntersecting) { animateCounters(); statsObs.disconnect(); }
}, { threshold: 0.3 });
const statsEl = document.querySelector('.hero-stats');
if (statsEl) statsObs.observe(statsEl);

// ══════════════════════════════
//  Particle System
// ══════════════════════════════
(function createParticles() {
  const c = document.getElementById('particles');
  if (!c) return;
  const cols = ['rgba(255,45,85,.6)', 'rgba(168,85,247,.6)', 'rgba(56,189,248,.4)', 'rgba(6,214,160,.4)'];
  for (let i = 0; i < 30; i++) {
    const p = document.createElement('div');
    p.className = 'particle';
    const sz = Math.random() * 4 + 1;
    Object.assign(p.style, {
      width: `${sz}px`, height: `${sz}px`,
      left:  `${Math.random() * 100}%`, bottom: '-10px',
      background: cols[Math.floor(Math.random() * cols.length)],
      animationDuration: `${Math.random() * 15 + 8}s`,
      animationDelay:    `${Math.random() * 10}s`,
      '--drift': `${(Math.random() - .5) * 200}px`,
    });
    c.appendChild(p);
  }
})();

// ══════════════════════════════
//  Extract YouTube Video ID
// ══════════════════════════════
function extractVideoId(url) {
  try {
    const u = new URL(url.trim());
    if (u.hostname === 'youtu.be') return u.pathname.slice(1).split('?')[0];
    if (u.hostname.includes('youtube.com')) {
      if (u.pathname === '/watch')           return u.searchParams.get('v');
      if (u.pathname.startsWith('/shorts/')) return u.pathname.split('/')[2];
      if (u.pathname.startsWith('/embed/'))  return u.pathname.split('/')[2];
    }
  } catch {
    const m = url.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }
  return null;
}

// ══════════════════════════════
//  Format helpers
// ══════════════════════════════
function fmtDuration(s) {
  if (!s) return '—';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}` : `${m}:${String(sec).padStart(2,'0')}`;
}
function fmtViews(n) {
  if (!n) return '—';
  if (n >= 1e9) return (n/1e9).toFixed(1)+'B views';
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M views';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K views';
  return n+' views';
}

// ══════════════════════════════
//  Status bar
// ══════════════════════════════
function showStatus(msg, type = 'error') {
  statusMsg.innerHTML = `<i class="bi bi-${type==='error'?'exclamation-circle-fill':'check-circle-fill'} me-2"></i>${msg}`;
  statusMsg.className = `status-msg ${type}`;
  statusMsg.classList.remove('d-none');
}
function hideStatus() { statusMsg.classList.add('d-none'); }

// ══════════════════════════════
//  Safe JSON Fetching Helper
// ══════════════════════════════
async function safeFetchJson(url, options = {}) {
  try {
    const resp = await fetch(url, options);
    
    // Check Content-Type header to make sure it's JSON
    const contentType = resp.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      const text = await resp.text();
      // If it looks like HTML, it's likely a 404 page from Live Server or server crash
      if (text.trim().startsWith('<')) {
        throw new Error('The server returned an HTML page instead of JSON.<br><br>' +
                        'This usually means the Python downloader server is not running on this port, ' +
                        'or you are opening the app via a static server (like VS Code Live Server).<br><br>' +
                        'Please make sure you started the backend by double-clicking "start.bat" ' +
                        'and are using the browser window that opened automatically.');
      }
      throw new Error(`Server returned non-JSON content: ${contentType || 'unknown type'}`);
    }
    
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.error || `Server responded with status ${resp.status}`);
    }
    return data;
  } catch (err) {
    // If it's already a descriptive error, rethrow it
    if (err.message && (err.message.includes('downloader server is not running') || err.message.includes('non-JSON content'))) {
      throw err;
    }
    // Network or other error
    throw new Error(`Failed to communicate with downloader server: ${err.message || err}`);
  }
}

// ══════════════════════════════
//  Render quality buttons
// ══════════════════════════════
function renderQualities(format) {
  qualityGrid.innerHTML = '';
  const savedQuality = localStorage.getItem(`yuvina_quality_${format}`);
  (qualityOptions[format] || []).forEach((q, i) => {
    const btn = document.createElement('button');
    btn.className = 'quality-btn' + (i === 0 ? ' best' : '');
    btn.textContent = q;
    const isSelected = savedQuality ? (q === savedQuality) : (i === 0);
    if (isSelected) { btn.classList.add('selected'); selectedQuality = q; }
    btn.addEventListener('click', () => {
      document.querySelectorAll('.quality-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected'); selectedQuality = q;
      localStorage.setItem(`yuvina_quality_${format}`, q);
    });
    qualityGrid.appendChild(btn);
  });
}

// ══════════════════════════════
//  Fetch video info
//  • Localhost → /api/info (yt-dlp, full metadata)
//  • file://   → YouTube oEmbed (basic, no download)
// ══════════════════════════════
async function fetchVideoInfo(videoId) {
  if (IS_SERVER) {
    const data = await safeFetchJson(`/api/info?id=${videoId}`);
    return {
      title:     data.title,
      channel:   data.channel,
      duration:  data.duration,
      views:     data.view_count,
      thumbnail: data.thumbnail || `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`,
    };
  }
  // Fallback: oEmbed (works without server, metadata only)
  const d = await safeFetchJson(
    `https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`
  );
  return {
    title:    d.title       || 'Unknown Title',
    channel:  d.author_name || 'Unknown Channel',
    duration: null, views: null,
    thumbnail: `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`,
  };
}

// ══════════════════════════════
//  Fetch button
// ══════════════════════════════
async function handleFetch() {
  const url = videoUrlInput.value.trim();
  if (!url)  { showStatus('Please paste a YouTube URL first.'); videoPreview.classList.add('d-none'); return; }
  const vid  = extractVideoId(url);
  if (!vid)  { showStatus('Invalid YouTube URL. Please check and try again.'); videoPreview.classList.add('d-none'); return; }

  fetchBtn.querySelector('.btn-fetch-text').classList.add('d-none');
  fetchBtn.querySelector('.btn-fetch-loader').classList.remove('d-none');
  fetchBtn.disabled = true;
  hideStatus();

  try {
    const info  = await fetchVideoInfo(vid);
    currentVideoId = vid;

    previewThumb.src            = info.thumbnail;
    previewTitle.textContent    = info.title;
    previewChannel.textContent  = info.channel;
    previewDuration.textContent = fmtDuration(info.duration);
    previewViews.textContent    = fmtViews(info.views);
    previewThumb.onerror = () => { previewThumb.src = `https://img.youtube.com/vi/${vid}/hqdefault.jpg`; };

    const savedFormat = localStorage.getItem('yuvina_format') || 'mp4';
    selectedFormat = ['mp4', 'mp3', 'webm'].includes(savedFormat) ? savedFormat : 'mp4';
    document.querySelectorAll('.format-tab').forEach(t => t.classList.toggle('active', t.dataset.type === selectedFormat));
    renderQualities(selectedFormat);

    videoPreview.classList.remove('d-none');
    showStatus('✓ Video found! Choose your format and quality below.', 'success');
  } catch (err) {
    showStatus(err.message || 'Something went wrong.');
    videoPreview.classList.add('d-none');
  } finally {
    fetchBtn.querySelector('.btn-fetch-text').classList.remove('d-none');
    fetchBtn.querySelector('.btn-fetch-loader').classList.add('d-none');
    fetchBtn.disabled = false;
  }
}

fetchBtn.addEventListener('click', handleFetch);
videoUrlInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleFetch(); });
videoUrlInput.addEventListener('paste', () => {
  setTimeout(() => { if (extractVideoId(videoUrlInput.value)) handleFetch(); }, 100);
});

// ══════════════════════════════
//  Paste Button
// ══════════════════════════════
pasteBtn.addEventListener('click', async () => {
  try {
    videoUrlInput.value = await navigator.clipboard.readText();
    videoUrlInput.focus();
    showToast('URL pasted from clipboard!');
  } catch { showToast('Could not access clipboard — paste manually.'); }
});

// ══════════════════════════════
//  Format Tabs
// ══════════════════════════════
document.querySelectorAll('.format-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.format-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    selectedFormat = tab.dataset.type;
    localStorage.setItem('yuvina_format', selectedFormat);
    renderQualities(selectedFormat);
  });
});

// ══════════════════════════════
//  Download Button & Real-time Progress Polling
// ══════════════════════════════
downloadBtn.addEventListener('click', async () => {
  if (!currentVideoId) { showToast('Please fetch a video first!'); return; }
  if (!selectedQuality) { showToast('Please select a quality first!'); return; }

  // Must be running via server
  if (!IS_SERVER) {
    showStatus(
      '⚠️ Downloads require the local server.<br>' +
      '<strong>Double-click <code>start.bat</code></strong> in the project folder ' +
      'to open the site correctly, then try again.',
      'error'
    );
    return;
  }

  const modalEl = document.getElementById('downloadModal');
  const modal   = new bootstrap.Modal(modalEl);
  
  // Reset modal elements before opening
  document.getElementById('dlModalTitle').textContent = 'Preparing Download…';
  document.getElementById('dlModalSub').textContent = 'Connecting to server…';
  dlProgressFill.style.width = '0%';
  dlProgressText.textContent = '0%';
  document.getElementById('dlDetails').classList.add('d-none');
  document.getElementById('dlModalAction').classList.add('d-none');
  
  const ring = document.getElementById('dlModalRing');
  const icon = document.getElementById('dlModalIcon');
  ring.style.display = 'block';
  icon.className = 'bi bi-cloud-arrow-down-fill dl-icon';
  icon.style.color = '';

  modal.show();

  let pollInterval = null;

  const cleanupAndClose = (status, errorMsg = '') => {
    if (pollInterval) clearInterval(pollInterval);
    ring.style.display = 'none';
    
    if (status === 'success') {
      icon.className = 'bi bi-check-circle-fill dl-icon text-success';
      document.getElementById('dlModalTitle').textContent = 'Completed!';
      document.getElementById('dlModalSub').textContent = 'Sent to your browser!';
      dlProgressFill.style.width = '100%';
      dlProgressText.textContent = '100%';
      document.getElementById('dlDetails').classList.add('d-none');
      
      // Auto-hide modal on success after 1.5 seconds
      setTimeout(() => {
        modal.hide();
      }, 1500);
    } else {
      icon.className = 'bi bi-exclamation-triangle-fill dl-icon text-danger';
      document.getElementById('dlModalTitle').textContent = 'Download Failed';
      document.getElementById('dlModalSub').innerHTML = `<span class="text-danger">${errorMsg || 'An unknown error occurred.'}</span>`;
      document.getElementById('dlModalAction').classList.remove('d-none'); // Show Close button
    }
  };

  try {
    // 1. Send download request to server to get task_id
    const startUrl = `/api/download?id=${currentVideoId}` +
                     `&format=${selectedFormat}` +
                     `&quality=${encodeURIComponent(selectedQuality)}`;
                     
    const { task_id } = await safeFetchJson(startUrl);
    if (!task_id) throw new Error('No task ID returned by the server.');

    // 2. Poll progress status endpoint
    pollInterval = setInterval(async () => {
      try {
        const data = await safeFetchJson(`/api/download/status?task_id=${task_id}`);
        
        if (data.status === 'downloading') {
          // Update progress bar & label
          dlProgressFill.style.width = data.progress + '%';
          dlProgressText.textContent = Math.round(data.progress) + '%';
          dlModalSub.textContent = data.phase || 'Downloading...';
          
          // Speed & ETA
          if (data.speed && data.eta) {
            document.getElementById('dlDetails').classList.remove('d-none');
            document.getElementById('dlSpeed').innerHTML = `<i class="bi bi-speedometer2 me-1"></i> ${data.speed}`;
            document.getElementById('dlETA').innerHTML = `<i class="bi bi-hourglass-split me-1"></i> ${data.eta}`;
          } else {
            document.getElementById('dlDetails').classList.add('d-none');
          }
        } 
        else if (data.status === 'completed') {
          cleanupAndClose('success');
          
          // Trigger the browser file download using the file streaming endpoint
          const fileUrl = `/api/download/file?task_id=${task_id}`;
          const a = document.createElement('a');
          a.href          = fileUrl;
          a.download      = data.filename || '';
          a.style.display = 'none';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);

          showStatus(
            `✓ Download completed successfully! Check your browser's download directory.`,
            'success'
          );
          showToast('✅ Download completed!');
        } 
        else if (data.status === 'failed') {
          cleanupAndClose('failed', data.error);
        }
      } catch (pollErr) {
        console.error('Error polling status:', pollErr);
        cleanupAndClose('failed', pollErr.message || 'Lost connection to the downloader server.');
      }
    }, 1000);

  } catch (err) {
    console.error('[YuvinaLoad] Start Error:', err);
    cleanupAndClose('failed', err.message);
  }
});

// ══════════════════════════════
//  Toast
// ══════════════════════════════
function showToast(message) {
  document.getElementById('toastBody').innerHTML =
    `<i class="bi bi-info-circle-fill me-2" style="color:var(--red-light)"></i>${message}`;
  new bootstrap.Toast(document.getElementById('liveToast'), { delay: 3500 }).show();
}

// ══════════════════════════════
//  Optimized Unified Scroll Handler
// ══════════════════════════════
const sections = document.querySelectorAll('section[id]');
const navPills = document.querySelectorAll('.nav-pill');
const mainNav = document.getElementById('mainNav');
let scrollTicking = false;

window.addEventListener('scroll', () => {
  if (!scrollTicking) {
    window.requestAnimationFrame(() => {
      // 1. Toggle scrolled class on navbar
      if (mainNav) {
        mainNav.classList.toggle('scrolled', window.scrollY > 60);
      }

      // 2. Update active nav pill
      let cur = '';
      sections.forEach(s => { if (s.getBoundingClientRect().top <= 100) cur = s.id; });
      navPills.forEach(l => {
        l.classList.remove('active');
        if (l.getAttribute('href') === `#${cur}`) l.classList.add('active');
      });

      scrollTicking = false;
    });
    scrollTicking = true;
  }
}, { passive: true });

// ══════════════════════════════
//  Scroll Reveal
// ══════════════════════════════
const rstyle = document.createElement('style');
rstyle.textContent = `.revealed{opacity:1!important;transform:translateY(0)!important}`;
document.head.appendChild(rstyle);

const revealObserver = new IntersectionObserver((entries, observer) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('revealed');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.15 });

document.querySelectorAll('.step-card, .feature-card').forEach(el => {
  el.style.cssText = 'opacity:0;transform:translateY(24px);transition:opacity .5s ease,transform .5s ease';
  revealObserver.observe(el);
});

// ══════════════════════════════
//  Newsletter
// ══════════════════════════════
document.querySelector('.newsletter-btn').addEventListener('click', () => {
  const inp = document.querySelector('.newsletter-input');
  if (!inp.value.trim().includes('@')) { showToast('Please enter a valid email.'); return; }
  showToast(`🎉 Thanks! You'll be notified at ${inp.value}`);
  inp.value = '';
});
