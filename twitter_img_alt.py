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
from __future__ import print_function
import itertools

def getSecrets(secrets_file='secrets'):
    """ Retrieve secrets from a file called 'secrets'.
        Returns a dict of keys.
    """
    with open(secrets_file, 'r') as f:
        return dict(
            itertools.imap(
                lambda x: (x[0].strip(), x[1].strip().strip('"\'')),
                itertools.ifilter(
                    lambda x: len(x) == 2 and x[0] is not None and x[1] is not None,
                    itertools.imap(
                        lambda line: tuple(line.split('=', 1)),
                        f.readlines()))))

class Mentions:
    """ Adapter for twitter API that retrieves mentions.
    """

    def __init__(self, twitterApi, since_id=None, status_file='state')
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
                self.since_id = self.status['since_id']

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
            _maybeUpdateStatusFile()

    def rawGetNewMentions(self):
        """ Gets new mentions, but does not do any state updates.
        """
        return self.twitterApi.GetMentions(
            count=200, # Max count
            since_id=self.since_id)

    def streaming(self, empty_sleep=60):
        """ Generator emitting one mention at a time.
        """
        import time.sleep

        while True:
            mentions = sorted(self.rawGetNewMentions(), key = lambda x: x.id)
            if len(mentions) == 0:
                sleep(empty_sleep)
            for m in mentions:
                self.since_id = m.id
                _maybeUpdateStatusFile()
                yield m

if __name__ == '__main__':
    import sys

    twitterApi = twitter.Api(tweet_mode='extended', sleep_on_rate_limit=True, **getSecrets())
    verify = twitterApi.VerifyCredentials()
    if verify is None:
        print('Invalid credentials\n')
        sys.exit(1)
    print(u'Verification success, logged in as: @{user.screen_name} (id={user.id}: {user.name})\n'.format(verify))

    for mention in Mentions(twitterApi):
        print mention
