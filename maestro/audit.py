#!/usr/bin/env python

import getpass


class BaseAuditor:
    """Base class for auditors that can save or notify about orchestration
    plays being executed."""

    def _format_action(self, what, action=None, who=None):
        if type(what) == list:
            what = ', '.join(what)
        who = who or getpass.getuser()

        if action:
            return '{} is {}ing {}.'.format(who, action, what)
        return '{} is acting on {}.'.format(who, what)

    def _format_success(self, what, action=None):
        if type(what) == list:
            what = ', '.join(what)

        if action:
            return '{} of {} succeeded.'.format(action.title(), what)
        return 'Action on {} succeeded.'.format(what)

    def _format_error(self, what, action=None, message=None):
        if type(what) == list:
            what = ', '.join(what)

        if action:
            s = 'Failed to {} {}!'.format(action, what)
        else:
            s = 'Failed action on {}!'.format(what)

        if message:
            s = '{} (message: {})'.format(s, message)
        return s

    def action(self, what, action=None, who=None):
        raise NotImplementedError

    def error(self, what, action=None, message=None):
        raise NotImplementedError


class HipChatAuditor(BaseAuditor):
    """Auditor that sends notifications in a HipChat chat room."""

    def __init__(self, name, room, token):
        self._name = name
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
        return HipChatAuditor(cfg['name'], cfg['room'], cfg['token'])


class LoggerAuditor(BaseAuditor):
    """Auditor that logs the notifications into a log file."""

    def __init__(self, filename):
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
        return LoggerAuditor(cfg['file'])


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
    }

    @staticmethod
    def from_config(cfg):
        auditors = set([])
        for auditor in cfg:
            auditors.add(AuditorFactory.AUDITORS[auditor['type']]
                         .from_config(auditor))
        return MultiplexAuditor(auditors)
