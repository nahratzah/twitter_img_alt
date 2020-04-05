#!/usr/bin/env python
# BSD 2-Clause License
#
# Copyright (c) 2017, Ariane van der Steldt
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import itertools
import twitter
import json
import logging

def _LOG():
    return logging.getLogger(__name__)

class BadAccess(Exception):
    def __init__(self, msg):
        BaseException.__init__(self)
        self.msg = msg

    def __str__(self):
        return self.msg

def getSecrets(secrets_file='secrets'):
    """ Retrieve secrets from a file called 'secrets'.
        Returns a dict of keys.
    """
    with open(secrets_file, 'r') as f:
        return dict(
            map(
                lambda x: (x[0].strip(), x[1].strip().strip('"\'')),
                filter(
                    lambda x: len(x) == 2 and x[0] is not None and x[1] is not None,
                    map(
                        lambda line: tuple(line.split('=', 1)),
                        f.readlines()))))

class Mentions:
    """ Adapter for twitter API that retrieves mentions.
    """

    def __init__(self, twitterApi, since_id=None, status_file='state'):
        """ Create a new mentions instance, using the specified twitter API.
            If since_id is not None, it will only evaluate mentions after that ID.

            If status_file is specified, it will retrieve the since_id from it
            and update it while progressing.
        """
        self.twitterApi = twitterApi
        self.since_id = since_id
        self.status_file = status_file
        self.status = dict() # File data

        if self.since_id is None and self.status_file is not None:
            with open(self.status_file, 'r') as f:
                self.status = json.load(f)
                try:
                    self.since_id = self.status['since_id']
                except KeyError:
                    pass

    def _maybeUpdateStatusFile(self):
        self.status['since_id'] = self.since_id
        if self.status_file is not None:
            with open(self.status_file, 'w') as f:
                json.dump(self.status, f)

    def getNewMentions(self):
        """ Get new mentions.
        """
        mentions = self.rawGetMentions()
        if len(mentions) > 0:
            self.since_id = max(mentions, lambda m: m.id)
            self._maybeUpdateStatusFile()

    def rawGetNewMentions(self):
        """ Gets new mentions, but does not do any state updates.
        """
        return self.twitterApi.GetMentions(
            count=200, # Max count
            since_id=self.since_id)

    def stream(self, empty_sleep=15):
        """ Generator emitting one mention at a time.
        """
        from time import sleep

        while True:
            mentions = sorted(self.rawGetNewMentions(), key = lambda x: x.id)
            if len(mentions) == 0:
                sleep(empty_sleep)
            for m in mentions:
                self.since_id = m.id
                self._maybeUpdateStatusFile()
                yield m

def generateAccessTokens():
    REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
    ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'
    AUTHORIZATION_URL = 'https://api.twitter.com/oauth/authorize'
    SIGNIN_URL = 'https://api.twitter.com/oauth/authenticate'

    from requests_oauthlib import OAuth1Session
    secrets = getSecrets()
    consumer_key = secrets['consumer_key']
    consumer_secret = secrets['consumer_secret']
    oauth_client = OAuth1Session(consumer_key, client_secret=consumer_secret, callback_uri='oob')
    try:
        resp = oauth_client.fetch_request_token(REQUEST_TOKEN_URL)
    except ValueError as e:
        raise BadAccess('Invalid response from Twitter requesting temp token: {0}'.format(e))

    url = oauth_client.authorization_url(AUTHORIZATION_URL)

    print('Please visit this URL to grant access:\n{0}\n'.format(url))
    pin = input('Pin code: ')

    oauth_client = OAuth1Session(consumer_key, client_secret=consumer_secret,
                                 resource_owner_key=resp.get('oauth_token'),
                                 resource_owner_secret=resp.get('oauth_token_secret'),
                                 verifier=pin)
    try:
        resp = oauth_client.fetch_access_token(ACCESS_TOKEN_URL)
    except ValueError as e:
        raise BadAccess('Invalid response from Twitter requesting temp token: {0}'.format(e))

    secrets['access_token_key'] = resp.get('oauth_token')
    secrets['access_token_secret'] = resp.get('oauth_token_secret')
    with open('secrets', 'w') as f:
        for (k, v) in secrets.items():
            f.write('{k} = {v}\n'.format(k=k, v=v))

def findParentOrQuotedTweet(twitterApi, tweet):
    """ Find the tweet this is a response to, or the quoted tweet.
    """
    if tweet.quoted_status is not None:
        return twitterApi.GetStatus(tweet.quoted_status.id)

    try:
        return twitterApi.GetStatus(tweet.AsDict()['in_reply_to_status_id'])
    except KeyError:
        return None

def createAnnotations(twitterApi, tweet):
    """ Generate annotations for a tweet.

        Returns a list of alt text.
        If the tweet contains no images, an empty list is returned.
    """
    try:
        media_images = [x for x in tweet.media if x.type in {'animated_gif', 'photo'}]
        if len(media_images) == 0:
            return list()
        alt_text_list = [img.ext_alt_text for img in media_images]
        if all([x is None for x in alt_text_list]):
            return ['''No alt text :'(''']
        return [x or 'Missing alt text' for x in alt_text_list]
    except TypeError:
        return list()

def annotationsToStatuses(annotations, maxlen):
    # Prefix annotations with image index, if there are more than one images.
    if len(annotations) > 1:
        annotations = ['Image {0}:\n{1}'.format(idx, txt)
            for (idx, txt) in zip(
                list(range(1, len(annotations) + 1)),
                [x for x in annotations])]

    result = list()
    for annot in annotations:
        annot = annot.strip()
        while len(annot) > maxlen:
            split_idx = annot.rfind('\n', 0, maxlen + 1)
            if split_idx == -1:
                split_idx = annot.rfind(' ', 0, maxlen + 1)

            if split_idx == -1: # Middle of word splitting.
                result.append(annot[:maxlen])
                annot = annot[maxlen:]
            else: # Splitting across line break or word.
                result.append(annot[:split_idx])
                annot = annot[split_idx+1:]
        result.append(annot)
    return result

def postReply(twitterApi, respondToTweet, text, user, self_user, first=True):
    """ Post a reply to the given tweet.
        If first is set, the automatic metadata is suppressed.
        Param users: list of users to reply to.
    """
    _LOG().info('Posting response to {respondToTweet.id}:\n------------------------------------------------------------------------\n{text}\n------------------------------------------------------------------------'.format(respondToTweet=respondToTweet, text=text))
    exclude=[x.id for x in respondToTweet.user_mentions if x.id not in [user.id, self.id]]
    _LOG().info('Excluding user IDs: {0}'.format(exclude))

    return twitterApi.PostUpdate(
        status='@{user.screen_name} {text}'.format(user=user, text=text),
        in_reply_to_status_id=respondToTweet.id,
        exclude_reply_user_ids=exclude,
        verify_status_length=False)

def annotateTweet(twitterApi, respondToTweet, toAnnotate, self):
    """ Annotate the tweet in toAnnotate.
    """
    user = respondToTweet.user

    annotations = createAnnotations(twitterApi, toAnnotate)
    if len(annotations) == 0:
        # postReply(twitterApi, respondToTweet, u'''Sorry, I don't see any images in the tweet.''', user, self)
        return

    statuses = annotationsToStatuses(annotations, 250)
    idx = 1
    if len(statuses) == 1: # Single reply, keep it short.
        postReply(twitterApi, respondToTweet, statuses[0], user, self)
    else: # Multiple replies, threaded.
        first_reply = True
        for (status, idx) in zip(statuses, list(range(1, len(statuses) + 1))):
            msg = '{0} [{1}/{2}]'.format(status.strip(), idx, len(statuses))
            respondToTweet = postReply(twitterApi, respondToTweet, msg, user, self, first_reply)
            first_reply = False # Don't clear metadata in subsequent responses.

def _setupLogging(path='logging.yml', default_level=logging.INFO):
    import yaml
    import os
    import logging.config

    if os.path.exists(path):
        with open(path, 'rt') as f:
            logging.config.dictConfig(yaml.safe_load(f.read()))
    else:
        logging.basicConfig(level=default_level)
        _LOG().warn('No {0} found.'.format(path))
    _LOG().info("Starting up, working dir = {0}".format(os.getcwd()))

if __name__ == '__main__':
    import sys

    _setupLogging()
    if False:
        generateAccessTokens()
        sys.exit(0)

    twitterApi = twitter.Api(tweet_mode='extended', sleep_on_rate_limit=True, **getSecrets())
    # self is the active user
    self = twitterApi.VerifyCredentials()
    if self is None:
        _LOG().error('Invalid credentials')
        sys.exit(1)
    _LOG().info('Verification success, logged in as: @{user.screen_name} (id={user.id}: {user.name})\n'.format(user=self))

    for mention in Mentions(twitterApi).stream():
        try:
            if mention.user.id != self.id:
                _LOG().info('tweet ID {mention.id} from @{mention.user.screen_name}: {mention.full_text}'.format(mention=mention))

                # Figure out which tweet to annotate.
                toAnnotate = findParentOrQuotedTweet(twitterApi, mention)
                if toAnnotate is not None:
                    annotateTweet(twitterApi, mention, toAnnotate, self)
                else:
                    _LOG().info('Nothing to annotate.')
                _LOG().info('Done processing tweet ID {mention.id}.\n'.format(mention=mention))
        except Exception:
            _LOG().exception('Failed to process https://twitter.com/{mention.user.screen_name}/status/{mention.id}'.format(mention=mention))
