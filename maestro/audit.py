# Copyright (C) 2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Docker container orchestration utility.

import getpass
import json
import logging
import requests
import six

from . import exceptions
from .version import name as maestro_name

# TODO(mpetazzoni): re-implement this with Logger/logging.handlers

DEBUG = logging.DEBUG
INFO = logging.INFO

DEFAULT_AUDIT_LEVEL = 'info'
_LEVELS_MAP = {
    'info': INFO,
    'debug': DEBUG,
}


class BaseAuditor(object):
    """Base class for auditors that can save or notify about orchestration
    plays being executed."""

    def __init__(self, level=DEBUG):
        if isinstance(level, six.string_types):
            level = _LEVELS_MAP[level]
        self._level = level

    @property
    def level(self):
        return self._level

    def _format_what(self, what):
        if type(what) == list or type(what) == tuple:
            return ', '.join(map(lambda e: e.name, what))
        return what.name

    def _format_who(self, who=None):
        return who or getpass.getuser()

    def _format_action_verb(self, action, end='ing'):
        if action == 'stop':
            action = 'stopp'
        return '{}{}'.format(action, end)

    def _format_action(self, what, action, who=None):
        what = self._format_what(what)
        action = self._format_action_verb(action)
        who = self._format_who(who)
        return '{} is {} {}.'.format(who, action, what)

    def _format_success(self, what, action):
        what = self._format_what(what)
        return '{} of {} succeeded.'.format(action.title(), what)

    def _format_error(self, what, action, message=None):
        what = self._format_what(what)

        s = 'Failed to {} {}!'.format(action, what)
        if message:
            s += ' (message: {})'.format(message)
        return s

    def _should_audit(self, level):
        return level >= self.level

    def action(self, level, what, action, who=None):
        raise NotImplementedError

    def success(self, level, what, action):
        raise NotImplementedError

    def error(self, what, action, message=None):
        raise NotImplementedError


class HipChatAuditor(BaseAuditor):
    """Auditor that sends notifications in a HipChat chat room."""

    def __init__(self, name, level, room, token):
        super(HipChatAuditor, self).__init__(level)
        if not room:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing HipChat room name!')
        if not token:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing HipChat API token!')

        self._name = name if name else maestro_name
        self._room = room

        import hipchat
        self._hc = hipchat.HipChat(token)

    def _message(self, params):
        self._hc.message_room(**params)

    def action(self, level, what, action, who=None):
        if not self._should_audit(level):
            return
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_action(what, action, who)
        })

    def success(self, level, what, action):
        if not self._should_audit(level):
            return
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_success(what, action),
            'color': 'green',
        })

    def error(self, what, action, message=None):
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_error(what, action, message),
            'color': 'red',
            'notify': True,
        })

    @staticmethod
    def from_config(cfg):
        return HipChatAuditor(
            cfg.get('name'),
            cfg.get('level', DEFAULT_AUDIT_LEVEL),
            cfg.get('room'),
            cfg.get('token'))


class SlackAuditor(BaseAuditor):
    """Auditor that sends notifications in a Slack channel."""

    def __init__(self, name, level, channel, token):
        super(SlackAuditor, self).__init__(level)
        if not channel:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing Slack channel name!')
        if not token:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing Slack bot token!')

        self._name = name if name else maestro_name
        self._channel = channel

        import slacker
        self._slack = slacker.Slacker(token)

    def _message(self, event):
        self._slack.chat.post_message(self._channel, None, username=self._name,
                                      attachments=[event])

    def action(self, level, what, action, who=None):
        if not self._should_audit(level):
            return
        self._message({
            'fallback': self._format_action(what, action, who),
            'color': '#1dc7d3',
            'fields': [
                {'title': 'Targets',
                 'value': self._format_what(what)},
                {'title': 'Status',
                 'value': self._format_action_verb(action).title(),
                 'short': True},
                {'title': 'Actor',
                 'value': self._format_who(who),
                 'short': True},
            ]
        })

    def success(self, level, what, action):
        if not self._should_audit(level):
            return
        self._message({
            'fallback': self._format_success(what, action),
            'color': 'good',
            'fields': [
                {'title': 'Targets',
                 'value': self._format_what(what)},
                {'title': 'Status',
                 'value': self._format_action_verb(action, end='ed').title(),
                 'short': True},
            ]
        })

    def error(self, what, action, message=None):
        self._message({
            'fallback': self._format_error(what, action, message),
            'color': 'danger',
            'fields': [
                {'title': 'Targets',
                 'value': self._format_what(what)},
                {'title': 'Status',
                 'value': 'Error',
                 'short': True},
                {'title': 'Error',
                 'value': message,
                 'short': True},
            ]
        })

    @staticmethod
    def from_config(cfg):
        return SlackAuditor(
            cfg.get('name'),
            cfg.get('level', DEFAULT_AUDIT_LEVEL),
            cfg.get('channel'),
            cfg.get('token'))


class LoggerAuditor(BaseAuditor):
    """Auditor that logs the notifications into a log file."""

    def __init__(self, filename, level):
        super(LoggerAuditor, self).__init__(level)
        if not filename:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing audit log filename!')

        import logging
        formatter = logging.Formatter(
            fmt='%(asctime)s %(levelname)s: %(message)s')
        handler = logging.FileHandler(filename)
        handler.setFormatter(formatter)

        self._logger = logging.getLogger('maestro')
        self._logger.addHandler(handler)
        self._logger.setLevel(self.level)

    def action(self, level, what, action, who=None):
        self._logger.log(level, self._format_action(what, action, who))

    def success(self, level, what, action):
        self._logger.log(level, self._format_success(what, action))

    def error(self, what, action, message=None):
        self._logger.error(self._format_error(what, action, message))

    @staticmethod
    def from_config(cfg):
        return LoggerAuditor(
            cfg.get('file'),
            cfg.get('level', DEFAULT_AUDIT_LEVEL))


class WebHookAuditor(BaseAuditor):
    """Auditor that makes HTTP calls, webhooks-style, with JSON payload."""

    DEFAULT_TIMEOUT = 3
    DEFAULT_HTTP_METHOD = 'POST'

    def __init__(self, endpoint, level, payload=None, headers=None,
                 method=DEFAULT_HTTP_METHOD, timeout=DEFAULT_TIMEOUT):
        super(WebHookAuditor, self).__init__(level)
        if not endpoint:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing webhook endpoint!')

        self._endpoint = endpoint
        self._payload = payload
        self._headers = {'Content-Type': 'application/json; charset=utf-8'}
        if headers:
            self._headers.update(headers)

        self._method = method.upper()
        if self._method not in ['GET', 'POST']:
            raise exceptions.InvalidAuditorConfigurationException(
                'Invalid HTTP method {}!'.format(method))
        self._timeout = timeout

    def _prepare_payload(self, what, action, who, message):
        what = self._format_what(what)
        who = self._format_who(who)

        def r(fn, on):
            if type(on) == dict:
                d = {}
                for k, v in on.items():
                    v2 = r(fn, v)
                    if v2:
                        d[k] = v2
                return d
            if type(on) == list or type(on) == tuple:
                return filter(None, map(fn, on))
            return fn(on)

        return r(lambda s: s.format(what=what, action=action, who=who,
                                    message=message),
                 self._payload)

    def action(self, level, what, action, who=None):
        if not self._should_audit(level):
            return
        payload = self._prepare_payload(what, action, who,
                                        self._format_action(what, action, who))
        if not payload:
            payload = None

        method = getattr(requests, self._method.lower())
        method(self._endpoint, headers=self._headers, data=json.dumps(payload),
               timeout=self._timeout)

    def success(self, level, what, action):
        pass

    def error(self, what, action, message=None):
        pass

    @staticmethod
    def from_config(cfg):
        return WebHookAuditor(
            cfg['endpoint'],
            cfg.get('level', DEFAULT_AUDIT_LEVEL),
            cfg.get('payload', {}),
            cfg.get('headers'),
            cfg.get('method', WebHookAuditor.DEFAULT_HTTP_METHOD),
            cfg.get('timeout', WebHookAuditor.DEFAULT_TIMEOUT))


class MultiplexAuditor(BaseAuditor):
    """Auditor multiplexer, to broadcast through multiple auditors."""

    def __init__(self, auditors):
        self._auditors = auditors

    def action(self, level, what, action, who=None):
        for auditor in self._auditors:
            try:
                auditor.action(level, what, action, who)
            except:
                raise

    def success(self, level, what, action):
        for auditor in self._auditors:
            try:
                auditor.success(level, what, action)
            except:
                pass

    def error(self, what, action, message=None):
        for auditor in self._auditors:
            try:
                auditor.error(what, action, message)
            except:
                pass


class AuditorFactory:

    AUDITORS = {
        'hipchat': HipChatAuditor,
        'slack': SlackAuditor,
        'log': LoggerAuditor,
        'http': WebHookAuditor,
    }

    @staticmethod
    def from_config(cfg):
        cfg = cfg or []
        auditors = []
        for auditor in cfg:
            if auditor['type'] not in AuditorFactory.AUDITORS:
                raise exceptions.InvalidAuditorConfigurationException(
                    'Unknown auditor type {}'.format(auditor['type']))
            auditors.append(AuditorFactory.AUDITORS[auditor['type']]
                            .from_config(auditor))
        return MultiplexAuditor(auditors)
