"""AH : Irfan - Live TV app (Kivy + Buildozer)."""
import re
import ssl
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.utils import get_color_from_hex, platform

import os

LAST_ERR = [""]


def is_android():
    return platform == "android" or "ANDROID_ROOT" in os.environ


def get_activity():
    """Works for Buildozer APKs and Pydroid 3."""
    from jnius import autoclass
    for cls in ("org.kivy.android.PythonActivity", "org.renpy.android.PythonActivity"):
        try:
            return autoclass(cls).mActivity
        except Exception:
            continue
    try:
        from android import mActivity  # some Pydroid builds
        return mActivity
    except Exception:
        pass
    raise RuntimeError("Android activity not found")


def run_on_ui(fn):
    """Run fn on the Android UI thread (no dependency on android.runnable)."""
    from jnius import PythonJavaClass, java_method

    class R(PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]
        __javacontext__ = "app"

        @java_method("()V")
        def run(self):
            try:
                fn()
            except Exception as e:
                LAST_ERR[0] = "ui: %s" % e

    r = R()
    _UI_REFS.append(r)
    get_activity().runOnUiThread(r)


_UI_REFS = []

BG = "#0F172A"
CARD = "#1E293B"
GOLD = "#FBBF24"

PLAYLISTS = [
    "https://iptv-org.github.io/iptv/countries/bd.m3u",
    "https://iptv-org.github.io/iptv/countries/in.m3u",
]

# Order here = order inside the priority block.
PRIORITY_KEYWORDS = [
    "&tv", "&pictures", "star jalsha", "jalsha movies", "zee bangla", "zee tv",
    "zee cinema", "zee anmol", "star plus", "star bharat", "star gold",
    "sony", "colors", "sab tv", "hbo", "sun bangla", "life ok",
]

# Players tried in order. (package, mime). Package None = system chooser.
HLS_MIME = "application/x-mpegURL"
PLAYER_ATTEMPTS = [
    ("org.videolan.vlc", HLS_MIME),
    ("com.mxtech.videoplayer.ad", HLS_MIME),
    ("com.mxtech.videoplayer.pro", HLS_MIME),
    (None, "video/*"),  # chooser: video apps only, browsers don't claim video/*
]

KV = """
<ChannelButton>:
    size_hint_y: None
    height: dp(64)
    background_normal: ''
    background_down: ''
    text_size: self.width - dp(16), self.height - dp(8)
    halign: 'center'
    valign: 'middle'
    max_lines: 2
    shorten: True
    shorten_from: 'right'
    font_size: sp(14)
    on_release: app.play(self.url, self.text)

<Root>:
    orientation: 'vertical'
    padding: dp(10)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: app.bg
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        size_hint_y: None
        height: dp(64)
        orientation: 'vertical'
        Label:
            text: 'AH : Irfan'
            bold: True
            font_size: sp(24)
            color: app.gold
        Label:
            id: counter
            text: root.status
            font_size: sp(13)
            color: 0.58, 0.64, 0.72, 1

    TextInput:
        id: search
        size_hint_y: None
        height: dp(44)
        hint_text: 'Search channels...'
        multiline: False
        padding: dp(12), dp(12)
        background_normal: ''
        background_active: ''
        background_color: app.card
        foreground_color: 1, 1, 1, 1
        hint_text_color: 0.5, 0.56, 0.65, 1
        cursor_color: app.gold
        on_text: root.apply_filter(self.text)

    RecycleView:
        id: rv
        viewclass: 'ChannelButton'
        bar_width: dp(4)
        RecycleGridLayout:
            cols: 2
            default_size: None, dp(64)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            spacing: dp(8)
            padding: 0, dp(4)
"""


class ChannelButton(Button):
    url = StringProperty("")


class Root(BoxLayout):
    status = StringProperty("Loading channels...")

    def __init__(self, **kw):
        super().__init__(**kw)
        self.channels = []
        threading.Thread(target=self._load, daemon=True).start()

    # ---------- loading (background thread) ----------
    def _load(self):
        with ThreadPoolExecutor(max_workers=len(PLAYLISTS)) as pool:
            results = list(pool.map(self._fetch, PLAYLISTS))
        failed = sum(1 for r in results if r is None)
        merged, seen = [], set()
        for text in results:
            if not text:
                continue
            for ch in parse_m3u(text):
                if ch["url"] not in seen:
                    seen.add(ch["url"])
                    merged.append(ch)
        merged = sort_channels(merged)
        Clock.schedule_once(lambda dt: self._loaded(merged, failed))

    @staticmethod
    def _fetch(url, retries=2):
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = ssl.create_default_context()
        for _ in range(retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AH-Irfan/1.0"})
                with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                    return r.read().decode("utf-8", errors="ignore")
            except Exception:
                continue
        return None

    # ---------- UI (main thread) ----------
    def _loaded(self, channels, failed):
        self.channels = channels
        self.apply_filter(self.ids.search.text)
        if not channels:
            self.status = "Could not load channels. Check your connection."
            return
        feat = sum(1 for c in channels if c["priority"])
        note = f"  ({failed} list failed)" if failed else ""
        self.status = f"{len(channels)} channels  |  {feat} featured{note}"

    def apply_filter(self, query):
        q = (query or "").strip().lower()
        rows = []
        for c in self.channels:
            if q and q not in c["name"].lower():
                continue
            if c["priority"]:
                rows.append({
                    "text": c["name"], "url": c["url"],
                    "background_color": get_color_from_hex(GOLD),
                    "color": get_color_from_hex(BG), "bold": True,
                })
            else:
                rows.append({
                    "text": c["name"], "url": c["url"],
                    "background_color": get_color_from_hex(CARD),
                    "color": (1, 1, 1, 1), "bold": False,
                })
        self.ids.rv.data = rows
        self.ids.rv.scroll_y = 1


# ---------- parsing / sorting ----------
HEADERS = {}  # url -> {"Referer":..., "User-Agent":...}


def parse_m3u(text):
    out, name, hdr = [], None, {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            name = line.rsplit(",", 1)[-1].strip() if "," in line else None
            if not name:
                m = re.search(r'tvg-name="([^"]+)"', line)
                name = m.group(1) if m else "Unknown"
        elif line.upper().startswith("#EXTVLCOPT:"):
            opt = line.split(":", 1)[1]
            k, _, v = opt.partition("=")
            k = k.strip().lower()
            if k == "http-referrer":
                hdr["Referer"] = v.strip()
            elif k == "http-user-agent":
                hdr["User-Agent"] = v.strip()
        elif line.startswith("#"):
            continue
        elif name is not None and line.lower().startswith(("http://", "https://")):
            out.append({"name": name, "url": line, "priority": False, "rank": 999})
            if hdr:
                HEADERS[line] = dict(hdr)
            name, hdr = None, {}
    return out


def sort_channels(channels):
    for c in channels:
        low = c["name"].lower()
        for i, kw in enumerate(PRIORITY_KEYWORDS):
            if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", low):
                c["priority"], c["rank"] = True, i
                break
    channels.sort(key=lambda c: (not c["priority"], c["rank"], c["name"].lower()))
    return channels


# ---------- Android player handoff ----------
def open_external_player(url):
    """Try VLC, MX Player, then system choosers. Returns True if an intent launched.

    Never sends a type-less http(s) VIEW intent (that would open a browser) and
    never forces video/mp4. Failures are caught per attempt so the next one runs.
    """
    if not is_android():
        LAST_ERR[0] = "not android"
        return False
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        activity = get_activity()
    except Exception as e:
        LAST_ERR[0] = "jnius: %s" % e
        return False
    uri = Uri.parse(url.strip())

    for package, mime in PLAYER_ATTEMPTS:
        try:
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, mime)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            if package:
                intent.setPackage(package)
                activity.startActivity(intent)
            else:
                chooser = Intent.createChooser(intent, "Play with...")
                chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                activity.startActivity(chooser)
            return True
        except Exception as e:
            LAST_ERR[0] = "intent: %s" % str(e)[:80]
            continue  # app missing / refused -> next attempt
    return False


# ---------- In-app native player (Android VideoView, handles HLS) ----------
class InAppPlayer:
    def __init__(self):
        self.layout = None
        self.vv = None
        self._refs = []
        self.last_error = ""

    @property
    def active(self):
        return self.layout is not None

    def open(self, url, on_fail):
        if not is_android():
            on_fail()
            return
        try:
            self._open_ui(url, on_fail)
        except Exception as e:
            LAST_ERR[0] = "player: %s" % e
            on_fail()

    def _open_ui(self, url, on_fail):
        def go():
            from jnius import autoclass, PythonJavaClass, java_method
            Color = autoclass("android.graphics.Color")
            Gravity = autoclass("android.view.Gravity")
            FrameLayout = autoclass("android.widget.FrameLayout")
            LP = autoclass("android.widget.FrameLayout$LayoutParams")
            VideoView = autoclass("android.widget.VideoView")
            ProgressBar = autoclass("android.widget.ProgressBar")
            MediaController = autoclass("android.widget.MediaController")
            Uri = autoclass("android.net.Uri")
            act = get_activity()

            player = self

            class Prepared(PythonJavaClass):
                __javainterfaces__ = ["android/media/MediaPlayer$OnPreparedListener"]
                __javacontext__ = "app"

                @java_method("(Landroid/media/MediaPlayer;)V")
                def onPrepared(self, mp):
                    spinner.setVisibility(8)  # GONE
                    player.vv.start()

            class Error(PythonJavaClass):
                __javainterfaces__ = ["android/media/MediaPlayer$OnErrorListener"]
                __javacontext__ = "app"

                @java_method("(Landroid/media/MediaPlayer;II)Z")
                def onError(self, mp, what, extra):
                    player.last_error = "%s/%s" % (what, extra)
                    player.close()
                    Clock.schedule_once(lambda dt: on_fail(), 0)
                    return True

            self.layout = FrameLayout(act)
            self.layout.setBackgroundColor(Color.BLACK)
            self.vv = VideoView(act)
            self.layout.addView(self.vv, LP(-1, -1, Gravity.CENTER))
            spinner = ProgressBar(act)
            self.layout.addView(spinner, LP(-2, -2, Gravity.CENTER))
            mc = MediaController(act)
            mc.setAnchorView(self.vv)
            self.vv.setMediaController(mc)
            prep, err = Prepared(), Error()
            self._refs = [prep, err, mc]  # keep alive (avoid GC)
            self.vv.setOnPreparedListener(prep)
            self.vv.setOnErrorListener(err)
            act.addContentView(self.layout, LP(-1, -1))
            hm = autoclass("java.util.HashMap")()
            for k, v in HEADERS.get(url, {}).items():
                hm.put(k, v)
            self.vv.setVideoURI(Uri.parse(url.strip()), hm)

        def safe():
            try:
                go()
            except Exception as e:
                LAST_ERR[0] = "player: %s" % str(e)[:80]
                self.layout = self.vv = None
                Clock.schedule_once(lambda dt: on_fail(), 0)

        run_on_ui(safe)

    def close(self):
        if not self.layout:
            return
        layout, vv = self.layout, self.vv
        self.layout = self.vv = None
        self._refs = []

        def go():
            from jnius import cast
            try:
                vv.stopPlayback()
                parent = layout.getParent()
                if parent:
                    cast("android.view.ViewGroup", parent).removeView(layout)
            except Exception:
                pass

        run_on_ui(go)


class AHIrfanApp(App):
    title = "AH : Irfan"
    bg = get_color_from_hex(BG)
    card = get_color_from_hex(CARD)
    gold = get_color_from_hex(GOLD)

    def build(self):
        Window.clearcolor = self.bg
        Window.bind(on_keyboard=self._on_key)
        self.player = InAppPlayer()
        Builder.load_string(KV)
        return Root()

    def _on_key(self, window, key, *args):
        if key == 27 and self.player.active:  # Android back button
            self.player.close()
            return True
        return False

    def play(self, url, name):
        if self.player.active:
            return

        def fallback():
            if not open_external_player(url):
                self._fallback_popup(url, name)

        self.player.open(url, fallback)  # in-app first, external on error

    def _fallback_popup(self, url, name):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        msg = Label(
            text="This stream could not be played (it may be offline or "
                 "blocked).\nTip: install VLC, or copy the link.\n"
                 "Error: " + (self.player.last_error or LAST_ERR[0] or "n/a"),
            halign="center", valign="middle")
        msg.bind(width=lambda w, v: setattr(w, "text_size", (v - dp(8), None)))
        box.add_widget(msg)
        copy = Button(text="Copy stream link", size_hint_y=None, height=dp(48))
        box.add_widget(copy)
        pop = Popup(title=name, content=box, size_hint=(0.9, 0.4))

        def do_copy(*_):
            Clipboard.copy(url)
            copy.text = "Copied!"
        copy.bind(on_release=do_copy)
        pop.open()


if __name__ == "__main__":
    AHIrfanApp().run()EExEx
