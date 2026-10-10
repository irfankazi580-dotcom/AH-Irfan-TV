import urllib.request
import re
import threading
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.video import Video
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock

class WorldTVApp(App):
    def build(self):
        self.title = "AH : Irfan"
        self.channels = {}

        # মূল লেআউট
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # টাইটেল
        self.title_label = Label(
            text="📺 AH : Irfan - Loading Channels...", 
            font_size='18sp', 
            size_hint=(1, 0.08),
            bold=True
        )
        main_layout.add_widget(self.title_label)

        # ভিডিও প্লেয়ার
        self.video_player = Video(
            source='',
            state='stop',
            options={'eos': 'loop'},
            size_hint=(1, 0.5)
        )
        main_layout.add_widget(self.video_player)

        # চ্যানেল বাটনগুলোর জন্য স্ক্রোলভিউ
        scroll = ScrollView(size_hint=(1, 0.42))
        self.channel_grid = GridLayout(cols=2, spacing=10, size_hint_y=None)
        self.channel_grid.bind(minimum_height=self.channel_grid.setter('height'))
        scroll.add_widget(self.channel_grid)

        main_layout.add_widget(scroll)

        # ব্যাকগ্রাউন্ডে চ্যানেল প্লেলিস্ট ডাউনলোড করা
        threading.Thread(target=self.load_iptv_playlists).start()

        return main_layout

    def load_iptv_playlists(self):
        urls = [
            "https://iptv-org.github.io/iptv/countries/bd.m3u", # বাংলাদেশ
            "https://iptv-org.github.io/iptv/countries/in.m3u"  # ইন্ডিয়া
        ]

        for url in urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    content = response.read().decode('utf-8')
                    matches = re.findall(r'#EXTINF:.*?,(.*?)\n(http[s]?://[^\s]+)', content)
                    for name, stream_url in matches:
                        clean_name = name.strip()
                        if clean_name and stream_url:
                            self.channels[clean_name] = stream_url
            except Exception as e:
                print(f"Error loading {url}: {e}")

        Clock.schedule_once(self.update_ui)

    def update_ui(self, dt):
        self.title_label.text = f"📺 AH : Irfan (Loaded: {len(self.channels)})"
        
        for channel_name in self.channels:
            btn = Button(
                text=channel_name[:20],
                size_hint_y=None,
                height=50,
                font_size='14sp',
                background_color=(0.2, 0.6, 1, 1)
            )
            btn.bind(on_press=lambda inst, name=channel_name: self.play_channel(name))
            self.channel_grid.add_widget(btn)

    def play_channel(self, channel_name):
        stream_url = self.channels.get(channel_name)
        if stream_url:
            self.video_player.state = 'stop'
            self.video_player.source = stream_url
            self.video_player.state = 'play'

if __name__ == '__main__':
    WorldTVApp().run()
