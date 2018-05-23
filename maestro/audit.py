# Copyright (C) 2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Docker container orchestration utility.

import getpass
import json
import logging
import requests
import six
import subprocess

from . import entities
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

    COMPACT_SIZE_LIMIT = 5

    def __init__(self, level=DEBUG):
        if isinstance(level, six.string_types):
            level = _LEVELS_MAP[level]
        self._level = level

    @property
    def level(self):
        return self._level

    def _fits_compact(self, what):
        return isinstance(what, entities.Entity) or \
            ((type(what) == list or type(what) == tuple) and
             len(what) < BaseAuditor.COMPACT_SIZE_LIMIT)

    def _format_what(self, what):
        if isinstance(what, entities.Entity):
            return what.name
        return ', '.join(map(lambda e: e.name, what))

    def _format_what_compact(self, what):
        if self._fits_compact(what):
            return self._format_what(what)
        return '{} container{}'.format(
            len(what), 's' if len(what) > 1 else '')

    def _format_who(self, who=None):
        return who or getpass.getuser()

    def _format_action_verb(self, action, end='ing'):
        if action == 'stop':
            action = 'stopp'
        return '{}{}'.format(action, end)

    def _format_action(self, what, action, who=None):
        action = self._format_action_verb(action)
        who = self._format_who(who)
        return '{} is {} {}.'.format(who, action, what)

    def _format_success(self, what, action):
        return '{} of {} succeeded.'.format(action.title(), what)

    def _format_error(self, what, action, message=None):
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


class _AlwaysFailAuditor(BaseAuditor):
    """Testing auditor that always fails."""
    def action(self, level, what, action, who=None):
        raise Exception

    def success(self, level, what, action):
        raise Exception

    def error(self, what, action, message=None):
        raise Exception

    @staticmethod
    def from_config(cfg):
        return _AlwaysFailAuditor()


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
            'message': self._format_action(
                self._format_what_compact(what),
                action, who)
        })

    def success(self, level, what, action):
        if not self._should_audit(level):
            return
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_success(
                self._format_what_compact(what),
                action),
            'color': 'green',
        })

    def error(self, what, action, message=None):
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_error(
                self._format_what_compact(what),
                action, message),
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

    def __init__(self, name, level, channel, token, icon=None):
        super(SlackAuditor, self).__init__(level)
        if not channel:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing Slack channel name!')
        if not token:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing Slack bot token!')

        self._name = name if name else maestro_name
        self._channel = channel
        self._icon = icon

        import slacker
        self._slack = slacker.Slacker(token)

    def _message(self, text, color, what, fields=None):
        event = {
            'fallback': text,
            'text': text,
            'color': color,
            'fields': fields or [],
        }
        if not self._fits_compact(what):
            event['fields'].append({
                'title': 'Targets',
                'value': self._format_what(what)
            })
        self._slack.chat.post_message(
            self._channel, None, username=self._name,
            icon_url=self._icon, attachments=[event])

    def action(self, level, what, action, who=None):
        if not self._should_audit(level):
            return
        text = self._format_action(
            self._format_what_compact(what),
            action, who)
        self._message(text, '#1dc7d3', what)

    def success(self, level, what, action):
        if not self._should_audit(level):
            return
        text = self._format_success(
            self._format_what_compact(what),
            action)
        self._message(text, 'good', what)

    def error(self, what, action, message=None):
        text = self._format_error(
            self._format_what_compact(what),
            action, message)
        self._message(text, 'danger', what, {
            'title': 'Error', 'value': message, 'short': True})

    @staticmethod
    def from_config(cfg):
        return SlackAuditor(
            cfg.get('name'),
            cfg.get('level', DEFAULT_AUDIT_LEVEL),
            cfg.get('channel'),
            cfg.get('token'),
            cfg.get('icon'))


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
        text = self._format_action(self._format_what(what), action, who)
        self._logger.log(level, text)

    def success(self, level, what, action):
        text = self._format_success(self._format_what(what), action)
        self._logger.log(level, text)

    def error(self, what, action, message=None):
        text = self._format_error(self._format_what(what), action, message)
        self._logger.error(text)

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
                return list(filter(None, map(lambda e: r(fn, e), on)))
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


class ExecuteScriptAuditor(BaseAuditor):
    """Auditor that executes scripts with maestro action information."""

    def __init__(self, script, args, level):
        super(ExecuteScriptAuditor, self).__init__(level)
        if not script:
            raise exceptions.InvalidAuditorConfigurationException(
                'Missing script to execute!')

        self._script = script
        self._args = args

    def _format_container_dict(self, what):
        d = {}
        for item in what:
            x = dict(ship=item.ship.ip, service=item.service.name)
            d[item.name] = x
        return json.dumps(d)

    def action(self, level, what, action, who):
        pass

    def success(self, level, what, action):
        if not self._should_audit(level):
            return
        if isinstance(what, entities.Entity):
            return
        ships = self._format_container_dict(what)

        cmd = [self._script] + \
            self._args.format(action=action, what=what, who=None).split()

        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        output = process.communicate(input=ships)
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.return_code,
                                                cmd, output)

    def error(self, what, action, message=None):
        pass

    @staticmethod
    def from_config(cfg):
        return ExecuteScriptAuditor(
            cfg.get('script'),
            cfg.get('args'),
            cfg.get('level', DEFAULT_AUDIT_LEVEL))


class MultiplexAuditor(BaseAuditor):
    """Auditor multiplexer, to broadcast through multiple auditors."""

    def __init__(self, auditors):
        self._auditors = auditors

    def get_auditors(self):
        return self._auditors

    def action(self, level, what, action, who=None):
        for auditor in self._auditors:
            try:
                auditor.action(level, what, action, who)
            except Exception:
                raise

    def success(self, level, what, action):
        for auditor in self._auditors:
            try:
                auditor.success(level, what, action)
            except Exception:
                pass

    def error(self, what, action, message=None):
        for auditor in self._auditors:
            try:
                auditor.error(what, action, message)
            except Exception:
                pass


class NonFailingAuditor(BaseAuditor):
    """A wrapper for another auditor that catches exceptions."""

    def __init__(self, auditor):
        self._auditor = auditor

    def action(self, level, what, action, who=None):
        try:
            self._auditor.action(level, what, action, who)
        except Exception:
            pass

    def success(self, level, what, action):
        try:
            self._auditor.success(level, what, action)
        except Exception:
            pass

    def error(self, what, action, message=None):
        try:
            self._auditor.error(what, action, message)
        except Exception:
            pass


class AuditorFactory:

    AUDITORS = {
        '_fail': _AlwaysFailAuditor,

        'hipchat': HipChatAuditor,
        'slack': SlackAuditor,
        'log': LoggerAuditor,
        'http': WebHookAuditor,
        'exec': ExecuteScriptAuditor,
    }

    @staticmethod
    def from_config(cfg):
        cfg = cfg or []
        auditors = []
        for auditor in cfg:
            if auditor['type'] not in AuditorFactory.AUDITORS:
                raise exceptions.InvalidAuditorConfigurationException(
                    'Unknown auditor type {}'.format(auditor['type']))
            impl = (AuditorFactory.AUDITORS[auditor['type']]
                    .from_config(auditor))
            if auditor.get('ignore_errors') is True:
                impl = NonFailingAuditor(impl)
            auditors.append(impl)
        return MultiplexAuditor(auditors)
