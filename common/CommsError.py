#!/usr/bin/env python
#
#  Copyright (c) 2001 Autonomous Zone Industries
#  This file is licensed under the
#    GNU Lesser General Public License v2.1.
#    See the file COPYING or visit http://www.gnu.org/ for details.
#

import exceptions

class Error(exceptions.StandardError): pass

class CannotSendError(Error): pass

class CannotListenError(Error): pass # for TCPCommsHandler, this means "couldn't bind to a port".

