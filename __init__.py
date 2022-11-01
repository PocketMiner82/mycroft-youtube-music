# The MIT License (MIT)
#
# Copyright (c) 2019 Drew Webber (mcdruid)
# Copyright (c) 2019 John Bartkiw
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import re
import pafy
import time

from ytmusicapi import YTMusic
from mtranslate import translate

from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel

# Static values for search requests
base_url = 'https://www.youtube.com'
search_url = base_url + '/results?search_query='

class YoutubeMusicSkill(CommonPlaySkill):

    def __init__(self):
        super().__init__(name='YoutubeMusicSkill')

        self.regexes = {}
        self.vid_id = None
        self.watch_results = None
        self.track_number = 0

    def initialize(self):
        # System events
        self.add_event("mycroft.audio.playing_track", self.handle_new_track)

    def CPS_match_query_phrase(self, phrase):
        """
        Look for regex matches starting from the most specific to the least

        Play <data> on youtube
        """
        match = re.search(self.translate_regex('on_youtube'), phrase)
        if match:
            data = re.sub(self.translate_regex('on_youtube'), '', phrase)
            self.log.debug('CPS Match (on_youtube): ' + data)
            return phrase, CPSMatchLevel.EXACT, data

        return phrase, CPSMatchLevel.GENERIC, phrase

    def CPS_start(self, phrase, data):
        self.log.debug('CPS Start: ' + data)
        self.search_youtube(data)

    def search_youtube(self, search_term):
        """
        Attempts to find the first result matching the query string
        """
        # check if we need to login
        pastedauth = self.settings.get('yt_auth_header')
        if(pastedauth and len(pastedauth)>10):
            YTMusic.setup(filepath=os.path.join(self.file_system.path, "headers_auth.json"), headers_raw=pastedauth)
            self.ytmusic = YTMusic(os.path.join(self.file_system.path, "headers_auth.json"))
        else:
            self.ytmusic = YTMusic()

        if re.search(self.translate_regex('in_english'), search_term):
            search_term = translate(re.sub(self.translate_regex('in_english'), '', search_term), "en", self.lang[:2])
            self.log.info(f"Autotranslate Result: {search_term}")

        # search youtube music for the song
        search_results = self.ytmusic.search(search_term, "songs", limit=1)

        # use the first result which has a video id
        if search_results:
            for vid in search_results:
                if not "videoId" in vid:
                    continue

                # play the song
                stream_url = self.get_song_stream_url(vid, True)
                if stream_url:
                    self.vid_id = vid["videoId"]
                    self.watch_results = self.ytmusic.get_watch_playlist(self.vid_id, limit=100)["tracks"]
                    self.audioservice.play(stream_url)
                    time.sleep(1)
                    self.handle_new_track()
                    return
                else:
                    break

        # we didn't find anything
        self.speak_dialog('not.found', wait=True)
        self.log.debug('Could not find any results with the query term: ' + search_term)
                
    
    def handle_new_track(self, ignored=None):
        # if we don't have results or no vid id or the track number is already 100: quit
        if not self.watch_results or not self.vid_id or self.track_number == 100:
            return

        # now try to add one more song from the watch playlist to the queue
        vid = self.watch_results[self.track_number]
        self.track_number += 1

        if not "videoId" in vid:
            return

        # try the next track if this is the same video the user requested to play
        if vid['videoId'] == self.vid_id:
            self.handle_new_track()
            return

        stream_url = self.get_song_stream_url(vid)
        if stream_url:
            self.audioservice.queue(stream_url)

    def get_song_stream_url(self, vid, speak_dialog=False):
        """
        This method tries to get the stream url for a video
        Parameters:
          vid - The video dict from ytmusicapi
          speak_dialog (optional) - should the dialog that the song is played be spoken
        """
        vid_id = vid['videoId']
        vid_uri = "/watch?v=" + str(vid_id)

        try:
            # get the video streams
            video = pafy.new(base_url + vid_uri)
            # select best audio stream
            stream_url = video.getbestaudio().url
            self.log.debug('Found stream URL: ' + stream_url)
            if speak_dialog:
                # speak the dialog, that we found the song and will play it
                self.speak_dialog('now.playing', {
                    'song': self.normalizeStr(vid['title']),
                    'artist': f" {self.translate('and')} ".join( [self.normalizeStr(artist["name"]) for artist in vid['artists']] )
                }, wait=True)
            return stream_url
        except Exception:
            return None
    
    def normalizeStr(self, val):
        """
        Replace stuff in the song title/artist for better tts output
        """
        return (val
            .replace("|", ":")
            .replace(" (", ", ")
            .replace(")", "")
            .replace("&", f" {self.translate('and')} ")
            .replace("  ", " ")
        )
    
    def stop(self):
        self.vid_id = None
        self.watch_results = None
        self.track_number = 0
        return super().stop()

    # Get the correct localized regex
    def translate_regex(self, regex):
        if regex not in self.regexes:
            path = self.find_resource(regex + '.regex')
            if path:
                with open(path) as f:
                    string = f.read().strip()
                self.regexes[regex] = string
        return self.regexes[regex]

def create_skill():
    return YoutubeMusicSkill()
