import sys
sys.path.append('..')

import time
import threading
from threading import Thread
import os
import sys
import signal

from spotify import ArtistBrowser, Link, ToplistBrowser, SpotifyError
from spotify.audiosink import import_audio_sink
from spotify.manager import (SpotifySessionManager, SpotifyPlaylistManager,
    SpotifyContainerManager)

import pusherclient

global pusher,session

AudioSink = import_audio_sink()
container_loaded = threading.Event()

APPKEY = '9e602ad8af30dac92ff2'
CHANNEL = 'jukebox_channel'

def print_usage(filename):
    print "Usage: python %s <appkey>" % filename
    
def stop_callback(data):
    session.stop()

def play_callback(data):
    track = data.strip('\"')
    print "Playing: %s" % track
    try:
        if track.startswith("spotify:"):
            l = Link.from_string(track)
            if not l.type() == Link.LINK_TRACK:
                print "Can only play tracks!"
                return
            session.load_track(l.as_track())
    except SpotifyError as e:
        print "Unable to load track:", e
        return
    session.play()

def connect_handler(data):
    channel = pusher.subscribe(CHANNEL)
    channel.bind('play', play_callback)
    channel.bind('stop', stop_callback)


## playlist callbacks ##
class JukeboxPlaylistManager(SpotifyPlaylistManager):
    def tracks_added(self, p, t, i, u):
        print 'Tracks added to playlist %s' % p.name()

    def tracks_moved(self, p, t, i, u):
        print 'Tracks moved in playlist %s' % p.name()

    def tracks_removed(self, p, t, u):
        print 'Tracks removed from playlist %s' % p.name()

## container calllbacks ##
class JukeboxContainerManager(SpotifyContainerManager):
    def container_loaded(self, c, u):
        container_loaded.set()

    def playlist_added(self, c, p, i, u):
        print 'Container: playlist "%s" added.' % p.name()

    def playlist_moved(self, c, p, oi, ni, u):
        print 'Container: playlist "%s" moved.' % p.name()

    def playlist_removed(self, c, p, i, u):
        print 'Container: playlist "%s" removed.' % p.name()

class Jukebox(SpotifySessionManager, threading.Thread):

    queued = False
    playlist = 2
    track = 0
    appkey_file = os.path.join(os.path.dirname(__file__), 'spotify_appkey.key')
    
    def __init__(self, *a, **kw):
        SpotifySessionManager.__init__(self, *a, **kw)
        threading.Thread.__init__(self)
        self.audio = AudioSink(backend=self)
        self.ctr = None
        self.playing = False
        self._queue = []
        self.playlist_manager = JukeboxPlaylistManager()
        self.container_manager = JukeboxContainerManager()
        self.track_playing = None
        print "Logging in, please wait..."
    
    def run(self):
        self.connect()
        
    def new_track_playing(self, track):
        self.track_playing = track
        
    def logged_in(self, session, error):
        if error:
            print error
            return
        print "Logged in!"
        self.ctr = session.playlist_container()
        self.container_manager.watch(self.ctr)
        self.starred = session.starred()
        
    def load_track(self, track):
        print u"Loading track..."
        while not track.is_loaded():
            time.sleep(0.1)
        if track.is_autolinked(): # if linked, load the target track instead
            print "Autolinked track, loading the linked-to track"
            return self.load_track(track.playable())
        if track.availability() != 1:
            print "Track not available (%s)" % track.availability()
        if self.playing:
            self.stop()
        self.new_track_playing(track)
        self.session.load(track)
        print "Loaded track: %s" % track.name()
        
    def play(self):
        self.audio.start()
        self.session.play(1)
        print "Playing"
        self.playing = True
        
    def stop(self):
        self.session.play(0)
        print "Stopping"
        self.playing = False
        self.audio.stop()
    
    def music_delivery_safe(self, *args, **kwargs):
        return self.audio.music_delivery(*args, **kwargs)

    def next(self):
        self.stop()
        if self._queue:
            t = self._queue.pop(0)
            self.load(*t)
            self.play()
        else:
            self.stop()

    def end_of_track(self, sess):
        self.audio.end_of_track()

if __name__ == '__main__':
    import optparse
    op = optparse.OptionParser(version="%prog 0.1")
    op.add_option("-u", "--username", help="Spotify username")
    op.add_option("-p", "--password", help="Spotify password")
    (options, args) = op.parse_args()
    
    session = Jukebox(options.username, options.password, True)
    session.start()
    
    pusher = pusherclient.Pusher(APPKEY)
    pusher.connection.bind('pusher:connection_established', connect_handler)
    
    def signal_handler(signal, frame):
        session.stop()
        session.disconnect()
        print "Goodbye"
        sys.exit()
        
    signal.signal(signal.SIGINT, signal_handler)
    
    while True:
        time.sleep(1)
