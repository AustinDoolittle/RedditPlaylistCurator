import re
import util
import pytz
import json
import praw
import spotipy
import spotipy.util as sp_util
from datetime import datetime
import dateutil.parser

def sanitize_song_name(post_title):
	return re.sub(r'(\[.*\]|\(\w+\d+\w+\)+|-)', '', post_title)

def is_song_link(post_link):
	return 'youtube' in post_link or 'youtu.be' in post_link or \
			'spotify' in post_link or 'bandcamp' in post_link

def parse_spotify_datetime(datetime_str):
	return dateutil.parser.parse(datetime_str)

def initialize_reddit_api(reddit_client_id, reddit_client_secret, reddit_user_agent):
	reddit = praw.Reddit(client_id=reddit_client_id,
		client_secret=reddit_client_secret,
		user_agent=reddit_user_agent)
	return reddit

def initialize_spotify_api(spotify_client_id, spotify_client_secret, spotify_username):
	# this scope allows us to create and modify public playlists
	scope='playlist-modify-public'
	token = sp_util.prompt_for_user_token(spotify_username, 
		scope,
		client_id=spotify_client_id,
		client_secret=spotify_client_secret,
		redirect_uri='https://www.google.com')

	# check that we were successful
	if not token:
		raise util.TokenException('There was an error retrieving the spotify token')

	spotify = spotipy.Spotify(auth=token)
	return spotify

class PlaylistCurator(object):
	def __init__(self, reddit_client_id, reddit_client_secret, reddit_user_agent,
				spotify_client_id, spotify_client_secret, spotify_username):
		self.reddit = initialize_reddit_api(reddit_client_id, reddit_client_secret, reddit_user_agent)
		self.spotify = initialize_spotify_api(spotify_client_id, spotify_client_secret, spotify_username)
		self.spotify_username = spotify_username
		self._config_dict = {}

	@staticmethod
	def load(config_file, *args, **kwargs):
		with open(config_file, 'r') as fp:
			config_dict = json.load(fp)
		retval = PlaylistCurator(*args, **kwargs)
		retval._config_dict = config_dict
		return retval

	def save(self, out_file):
		with open(out_file, 'w') as fp:
			json.dump(self._config_dict, fp, indent=4, sort_keys=True)

	def __str__(self):
		ret_str = ''
		for playlist_id, playlist_settings in self._config_dict.items():
			ret_str += 'Playlist ID: %s\n'%playlist_id
			ret_str += '\tTop N: %i posts\n'%playlist_settings['top_n']
			ret_str += '\tExpire Days: %i days\n'%playlist_settings['expire_days']
			ret_str += '\tSubreddit(s): %s\n\n'%(', '.join(playlist_settings['subreddits']))
		return ret_str

	def update(self, playlist_id, top_n=None, expire_days=None, subreddits=None):
		if not self.contains_playlist(playlist_id):
			raise ValueError('This configuration does not contain playlist id %s'%playlist_id)

		update_dict = {}
		if not top_n is None:
			update_dict['top_n'] = top_n

		if not expire_days is None:
			update_dict['expire_days'] = expire_days

		if not subreddits is None:
			update_dict['subreddits'] = subreddits

		self._config_dict[playlist_id].update(update_dict)

	def add(self, playlist_id=None, playlist_name=None, top_n=25, expire_days=7, subreddits=None):
		# validate our input
		if not playlist_id ^ playlist_name:
			raise ArgumentError('You must specify one and only one of the following arguments: "playlist_name", "playlist_id"')

		if not subreddits:
			raise ArgumentError('Missing argument "subreddits"')

		# check whether we should use a preexisting playlist or create a new one
		if playlist_id:
			# ensure that we don't already have this playlist
			if self.contains_playlist(playlist_id):
				raise ValueError('This configuration already contains a playlist with the id %s'%playlist_id)

			# TODO validate the playlist exists and we have permissions to edit it
			# if not self._valid_playlist(playlist_id):
			# 	raise ValueError('Playlist with id %s either does not exist or Spotify username %s does not have write access'%(playlist_id, self.spotify_username))
		else:
			# create the playlist
			new_playlist = self.spotify.user_playlist_create(self.spotify_username, 
				playlist_name,
				public=True)
			playlist_id = new_playlist['id']

		self._config_dict[playlist_id] = {
			'top_n': top_n,
			'expire_days': expire_days,
			'subreddits': subreddits
		}


	def _is_valid_playlist_id(self, playlist_id):
		raise NotImplemented()

	def contains_playlist(self, playlist_id):
		return playlist_id in self._config_dict

	def _trim_expired_from_playlist(self, playlist_id, expire_days):
		# get the playlist tracks
		playlist = self.spotify.user_playlist(self.spotify_username, playlist_id, fields='tracks,next')
		playlist_tracks = playlist['tracks']

		# have one unified start time for consistency
		start_time = datetime.now(pytz.utc)
		remove_tracks = []

		# iterate until pagination stops
		while True:
			# iterate over the tracks in the current response
			for track in playlist_tracks['items']:
				# figure out when it was added
				added_at = parse_spotify_datetime(track['added_at'])
				days_since_added = (start_time - added_at).days

				# if we are over expiration days, add this track to be removed
				if days_since_added > expire_days:
					remove_tracks.append(track['id'])

			# check for termination condition
			if playlist_tracks['next'] is None:
				break

			# retrieve the next page
			playlist_tracks = self.spotify.next(playlist_tracks['next'])
		
		# if we have tracks to remove, do it
		if remove_tracks:
			self.spotify.user_playlist_remoe_all_occurrences_of_tracks(self.spotify_username, playlist_id, remove_tracks)

	def _add_top_posts(self, subreddits, playlist_id, top_n):
		# add top posts from today
		songs_to_add = []
		for subreddit in subreddits:
			for post in self.reddit.subreddit(subreddit).top('day', limit=None):
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


	def curate(self):
		#clear out songs that are currently in the playlist that have been there longer than *expire_days*
		for playlist_id, config_dict in self._config_dict.items():
			if config_dict['expire_days'] >= 0:
				self._trim_expired_from_playlist(playlist_id, config_dict['expire_days'])

			# add new songs
			self._add_top_posts(config_dict['subreddits'], playlist_id, config_dict['top_n'])


