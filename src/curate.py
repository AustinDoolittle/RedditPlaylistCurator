import re
import util
import pytz
from datetime import datetime
import dateutil.parser

def sanitize_song_name(post_title):
	return re.sub(r'(\[.*\]|\(\w+\d+\w+\)+|-)', '', post_title)

def is_song_link(post_link):
	return 'youtube' in post_link or 'youtu.be' in post_link

def parse_spotify_datetime(datetime_str):
	return dateutil.parser.parse(datetime_str)

class PlaylistCurator(object):
	def __init__(self, reddit, spotify, spotify_username):
		self.reddit = reddit
		self.spotify = spotify
		self.spotify_username = spotify_username

	def _trim_expired_from_playlist(self, playlist_id, expire_days):
		playlist = self.spotify.user_playlist(self.spotify_username, playlist_id, fields='tracks,next')
		playlist_tracks = playlist['tracks']
		start_time = datetime.now(pytz.utc)
		remove_tracks = []
		while True:
			for track in playlist_tracks['items']:
				added_at = parse_spotify_datetime(track['added_at'])
				days_since_added = (start_time - added_at).days
				if days_since_added > expire_days:
					remove_tracks.append(track['id'])

			if playlist_tracks['next'] is None:
				break

			playlist_tracks = self.spotify.next(playlist_tracks['next'])
		
		if remove_tracks:
			self.spotify.user_playlist_remoe_all_occurrences_of_tracks(self.spotify_username, playlist_id, remove_tracks)

	def _add_top_posts(self, subreddit, playlist_id, top_n, time_filter='day'):
		# add top posts from today
		songs_to_add = []
		for post in self.reddit.subreddit(subreddit).top(time_filter, limit=None):
			if not is_song_link(post.url):
				# this isn't a youtube link, it's fair to assume this isn't a song
				continue

			# sanitize our title and search spotify for a match
			sanitized_title = sanitize_song_name(post.title)
			search_result = self.spotify.search(q=sanitized_title, type='track')

			# check the case that no valid items were returnd
			if len(search_result['tracks']['items']) == 0:
				continue

			# get the first result and add it to our playlist
			songs_to_add.append(search_result['tracks']['items'][0]['id'])
			if len(songs_to_add) == top_n:
				break

		if songs_to_add:
			self.spotify.user_playlist_add_tracks(self.spotify_username, playlist_id, songs_to_add)


	def curate_playlist(self, subreddit, playlist_id=None, top_n=25, expire_days=7, time_filter='day'):
		#clear out songs that are currently in the playlist that have been there longer than *expire_days*
		self._trim_expired_from_playlist(playlist_id, expire_days)

		# add new songs
		self._add_top_posts(subreddit, playlist_id, top_n, time_filter)


