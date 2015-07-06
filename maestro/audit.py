# Copyright (C) 2014 SignalFuse, Inc.
# Copyright (C) 2015 SignalFx, Inc.
#
# Docker container orchestration utility.

import getpass
import json
import requests

from . import exceptions
from .version import name as maestro_name


class BaseAuditor:
    """Base class for auditors that can save or notify about orchestration
    plays being executed."""

    def _format_what(self, what):
        if type(what) == list or type(what) == tuple:
            return ', '.join(what)
        return what

    def _format_who(self, who=None):
        return who or getpass.getuser()

    def _format_action(self, what, action=None, who=None):
        what = self._format_what(what)
        who = self._format_who(who)

        if action:
            action = action if action is not 'stop' else 'stopp'
            return '{} is {}ing {}.'.format(who, action, what)
        return '{} is acting on {}.'.format(who, what)

    def _format_success(self, what, action=None):
        what = self._format_what(what)

        if action:
            return '{} of {} succeeded.'.format(action.title(), what)
        return 'Action on {} succeeded.'.format(what)

    def _format_error(self, what, action=None, message=None):
        what = self._format_what(what)

        if action:
            s = 'Failed to {} {}!'.format(action, what)
        else:
            s = 'Failed action on {}!'.format(what)

        if message:
            s = '{} (message: {})'.format(s, message)
        return s

    def action(self, what, action=None, who=None):
        raise NotImplementedError

    def success(self, what, action=None):
        raise NotImplementedError

    def error(self, what, action=None, message=None):
        raise NotImplementedError


class HipChatAuditor(BaseAuditor):
    """Auditor that sends notifications in a HipChat chat room."""

    def __init__(self, name, room, token):
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

    def action(self, what, action=None, who=None):
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_action(what, action, who)
        })

    def success(self, what, action=None):
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_success(what, action),
            'color': 'green',
        })

    def error(self, what, action=None, message=None):
        self._message({
            'room_id': self._room,
            'message_from': self._name,
            'message': self._format_error(what, action, message),
            'color': 'red',
            'notify': True,
        })

    @staticmethod
    def from_config(cfg):
        return HipChatAuditor(cfg.get('name'), cfg.get('room'),
                              cfg.get('token'))


class LoggerAuditor(BaseAuditor):
    """Auditor that logs the notifications into a log file."""

    def __init__(self, filename):
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
        self._logger.setLevel(logging.INFO)

    def action(self, what, action=None, who=None):
        self._logger.info(self._format_action(what, action, who))

    def success(self, what, action=None):
        self._logger.info(self._format_success(what, action))

    def error(self, what, action=None, message=None):
        self._logger.error(self._format_error(what, action, message))

    @staticmethod
    def from_config(cfg):
        return LoggerAuditor(cfg.get('file'))


class WebHookAuditor(BaseAuditor):
    """Auditor that makes HTTP calls, webhooks-style, with JSON payload."""

    DEFAULT_TIMEOUT = 3
    DEFAULT_HTTP_METHOD = 'POST'

    def __init__(self, endpoint, payload=None, headers=None,
                 method=DEFAULT_HTTP_METHOD, timeout=DEFAULT_TIMEOUT):
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

    def action(self, what, action=None, who=None):
        payload = self._prepare_payload(what, action, who,
                                        self._format_action(what, action, who))
        if not payload:
            payload = None

        method = getattr(requests, self._method.lower())
        method(self._endpoint, headers=self._headers, data=json.dumps(payload),
               timeout=self._timeout)

    def success(self, what, action=None):
        pass

    def error(self, what, action=None, message=None):
        pass

    @staticmethod
    def from_config(cfg):
        return WebHookAuditor(
            cfg['endpoint'],
            cfg.get('payload', {}),
            cfg.get('headers'),
            cfg.get('method', WebHookAuditor.DEFAULT_HTTP_METHOD),
            cfg.get('timeout', WebHookAuditor.DEFAULT_TIMEOUT))


class MultiplexAuditor(BaseAuditor):
    """Auditor multiplexer, to broadcast through multiple auditors."""

    def __init__(self, auditors):
        self._auditors = auditors

    def action(self, what, action=None, who=None):
        for auditor in self._auditors:
            try:
                auditor.action(what, action, who)
            except:
                pass

    def success(self, what, action=None):
        for auditor in self._auditors:
            try:
                auditor.success(what, action)
            except:
                pass

    def error(self, what, action=None, message=None):
        for auditor in self._auditors:
            try:
                auditor.error(what, action, message)
            except:
                pass


class AuditorFactory:

    AUDITORS = {
        'hipchat': HipChatAuditor,
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
