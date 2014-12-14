
# ________________________________________________________________________
#
#  Copyright (C) 2014 Andrew Fullford
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ________________________________________________________________________
#

import os, logging

def logger():
	handler = logging.StreamHandler()
	handler.setFormatter(logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s"))
	log = logging.getLogger(__name__)
	log.addHandler(handler)
	log_level = logging.INFO

	#  This cuts the logging noise in the travis output.
	#  Set TRAVIS_LOG_LEVEL in .travis.yml
	#
	try:
		if 'TRAVIS_LOG_LEVEL' in os.environ:
			log_level = int(os.environ['TRAVIS_LOG_LEVEL'])
	except:
		pass
	log.setLevel(log_level)
	return log
