"""HTML pieces for the compact song cards: the custom audio player and the match bar.

Plain functions with no Streamlit in them, so they can be unit tested. The player is
shown with st.iframe, which runs the HTML as-is with same-origin access to the app,
so player_html() only accepts plain https URLs and escapes them.
"""
import html
from typing import Optional

PLAYER_HEIGHT = 190


def match_chip(pct: int) -> str:
    return f'<span class="chip chip-match">{int(pct)}% match</span>'


def match_bar(pct: int) -> str:
    """A thin gradient bar showing the match percentage."""
    pct = max(0, min(100, int(pct)))
    return f'<div class="match-bar"><div style="width:{pct}%"></div></div>'


def art_placeholder_html() -> str:
    """Square stand-in shown when a song has no album art or preview."""
    return '<div class="art-placeholder">&#9834;</div>'


_PLAYER_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:transparent;font-family:system-ui,sans-serif;color:#B9B3D9}
.art{position:relative;width:140px;height:140px;border-radius:16px;overflow:hidden;
  background:linear-gradient(135deg,#2a2160,#17173A) center/cover no-repeat;
  border:1px solid rgba(157,123,255,.6);box-shadow:0 6px 20px rgba(157,123,255,.35)}
.art.has-img{background-image:url("__ART__")}
.note{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-size:48px;color:rgba(255,255,255,.25)}
.btn{position:absolute;left:50%;top:50%;width:52px;height:52px;margin:-26px 0 0 -26px;
  border-radius:50%;border:none;cursor:pointer;color:#fff;font-size:20px;
  background:rgba(11,11,26,.7);transition:all .15s ease;box-shadow:0 2px 10px rgba(0,0,0,.5)}
.art:hover .btn,.btn:focus-visible{background:#9D7BFF;transform:scale(1.08);outline:none}
.bar{width:140px;height:5px;margin-top:10px;border-radius:3px;background:rgba(255,255,255,.15);cursor:pointer}
.fill{height:100%;width:0;border-radius:3px;background:linear-gradient(90deg,#9D7BFF,#F2B84B)}
.time{width:140px;margin-top:5px;font-size:11px;display:flex;justify-content:space-between}
</style></head><body>
<div class="art __IMGCLASS__"><div class="note">&#9834;</div>
<button class="btn" id="btn" aria-label="Play or pause preview">&#9654;</button></div>
<div class="bar" id="bar"><div class="fill" id="fill"></div></div>
<div class="time"><span id="t">0:00</span><span>Apple Music preview</span></div>
<audio id="a" preload="none" src="__AUDIO__"></audio>
<script>
const a=document.getElementById('a'),btn=document.getElementById('btn'),
  fill=document.getElementById('fill'),bar=document.getElementById('bar'),t=document.getElementById('t');
const me=Math.random().toString(36).slice(2);
let ch=null; try{ch=new BroadcastChannel('symphonysearch-player');}catch(e){}
const fmt=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
btn.onclick=()=>{ if(a.paused){ if(ch)ch.postMessage(me); a.play().catch(()=>{}); } else a.pause(); };
if(ch) ch.onmessage=e=>{ if(e.data!==me) a.pause(); };   // only one preview plays at a time
a.onplay=()=>btn.innerHTML='&#10074;&#10074;';
a.onpause=()=>btn.innerHTML='&#9654;';
a.onended=()=>{btn.innerHTML='&#9654;';fill.style.width='0';t.textContent='0:00';};
a.ontimeupdate=()=>{const d=a.duration||30;fill.style.width=(a.currentTime/d*100)+'%';t.textContent=fmt(a.currentTime);};
bar.onclick=e=>{const r=bar.getBoundingClientRect();a.currentTime=((e.clientX-r.left)/r.width)*(a.duration||30);};
</script></body></html>"""


def _safe_https(url: Optional[str]) -> str:
    bad_chars = '"<>\\ \n\r'
    if not isinstance(url, str) or not url.startswith("https://") or any(c in url for c in bad_chars):
        raise ValueError("player URLs must be plain https URLs")
    return html.escape(url, quote=True)


def player_html(audio_url: str, art_url: Optional[str] = None) -> str:
    """Album art with a play/pause button on top, a seek bar, and a timer.

    Raises ValueError for anything that is not a plain https URL.
    """
    page = _PLAYER_TEMPLATE.replace("__AUDIO__", _safe_https(audio_url))
    if art_url:
        return page.replace("__ART__", _safe_https(art_url)).replace("__IMGCLASS__", "has-img")
    return page.replace("__ART__", "").replace("__IMGCLASS__", "")
