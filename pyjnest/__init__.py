# -*- mode: python; coding: utf-8 -*-

import json
import requests
import logging

logger = logging.getLogger('pyenest')

class Connection(object):
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.headers = {'User-Agent': 'Nest/1.1.0.10 CFNetwork/548.0.4'}

        # all the users ever seen on this connection
        self._users = {}

        # all the devices ever seen on this connection
        self._devices = {}

        # all the structures ever seen on this connection
        self._structures = {}

    def login(self):
        logger.debug('logging in {}'.format(self.username))
        data = {'username': self.username,
                'password': self.password}

        r = requests.post('https://home.nest.com/user/login',
                          data = data,
                          headers = self.headers)
        res = r.json()

        self.transport_url = res['urls']['transport_url']
        self.access_token = res['access_token']
        self.userid = res['userid']

        self.headers['Authorization'] = 'Basic ' + self.access_token
        self.headers['X-nl-user-id'] = self.userid
        self.headers['X-nl-protocol-version'] = '1'

        self.update_status()

    def update_status(self):
        r = requests.get(self.transport_url + '/v2/mobile/user.{}'.format(self.userid),
                         headers = self.headers)

        self.status = r.json()

    @property
    def devices(self):
        return {device_id: Device.get(self, device_id) for device_id in self.status['device'].keys()}

    @property
    def links(self):
        return [(Device.get(self, device_id), Structure.get(self, data['structure'])) for device_id, data in self.status['link'].items()]

    @property
    def users(self):
        return {user_id: User.get(self, user_id) for user_id in self.status['user'].keys()}

    @property
    def structures(self):
        structure_ids = set([structure.structure_id for device, structure in self.links])
        return {structure_id: Structure.get(self, structure_id) for structure_id in structure_ids}

class User(object):
    @classmethod
    def get(klass, connection, user_id):
        if user_id in connection._users:
            return connection._users[user_id]
        return klass(connection, user_id)

    def __init__(self, connection, user_id):
        self.connection = connection
        self.user_id = user_id
        self.connection._users[self.user_id] = self

    def __getattr__(self, name):
        if name.startswith('_'):
            name = '$' + name[1:]
        data = self.connection.status['user'][self.user_id]
        if name in data:
            return data[name]
    
        raise AttributeError

    @property
    def settings(self):
        return UserSettings.get(self.connection, self.user_id)

    @property
    def structures(self):
        return {Structure.clean_id(structure_id): Structure.get(self.connection, structure_id) for structure_id in self.connection.status['user'][self.user_id]['structures']}

class UserSettings(object):
    @classmethod
    def get(klass, connection, user_id):
        if user_id in connection._user_settings:
            return connection._user_settings[user_id]
        return klass(connection, user_id)

    def __init__(self, connection, user_id):
        self.connection = connection
        self.user_id = user_id
        self.connection._user_settings[self.user_id] = self

    def __getattr__(self, name):
        if name.startswith('_'):
            name = '$' + name[1:]
        data = self.connection.status['user_settings'][self.user_id]
        if name in data:
            return data[name]
    
        raise AttributeError

    @property
    def user(self):
        return User.get(self.connection, self.user_id)

class Device(object):
    @classmethod
    def get(klass, connection, device_id):
        if device_id in connection._devices:
            return connection._devices[device_id]
        return klass(connection, device_id)
        
    def __init__(self, connection, device_id):
        self.connection = connection
        self.device_id = device_id
        self.connection._devices[self.device_id] = self
        self._fan_mode = None

    def __getattr__(self, name):
        if name.startswith('_'):
            name = '$' + name[1:]

        data = self.connection.status['device'][self.device_id]
        if name in data:
            return data[name]

        shared = self.connection.status['shared'][self.device_id]
        if name in shared:
            return shared[name]

        raise AttributeError

    @property
    def structure(self):
        return Structure.get(self.connection,
                             self.connection.status['link'][self.device_id]['structure'])

    @property
    def data(self):
        return self.connection.status['device'][self.device_id]

    @property
    def fan_mode(self):
        return self._fan_mode

    @fan_mode.setter
    def fan_mode(self, mode):
        self._fan_mode = mode
        data = {'fan_mode': (self.fan_mode)}

        headers = self.connection.headers.copy()
        headers['Content-Type'] = 'application/json'

        r = requests.post(self.connection.transport_url + '/v2/put/device.{}'.format(self.device_id),
                          data = json.dumps(data),
                          headers = headers)

        print r.status_code
        print r.text


    def toggle_fan(self):
        mode == 'on' if self.fan_mode == 'auto' else 'auto'
        self.fan_mode = mode

    def change_temperature(self, delta = 0, target_type = 'target_temperature'):
        old_target = getattr(self, target_type)
        new_target = old_target + delta

        data = {'target_change_pending': True,
                target_type: '{:0.1f}'.format(new_target)}

        headers = self.connection.headers.copy()
        headers['Content-Type'] = 'application/json'

        r = requests.post(self.connection.transport_url + '/v2/put/shared.{}'.format(self.device_id),
                          data = json.dumps(data),
                          headers = headers)

        print r.status_code
        print r.text

class Structure(object):
    @classmethod
    def clean_id(klass, structure_id):
        if structure_id.startswith('structure.'):
            return structure_id[10:]
        return structure_id

    @classmethod
    def get(klass, connection, structure_id):
        structure_id = klass.clean_id(structure_id)

        if structure_id in connection._structures:
            return connection._structures[structure_id]

        return klass(connection, structure_id)

    def __init__(self, connection, structure_id):
        structure_id = self.clean_id(structure_id)

        self.connection = connection
        self.structure_id = structure_id
        self.connection._structures[self.structure_id] = self

    def __repr__(self):
        return 'Structure(\'{}\')'.format(self.structure_id)

    @property
    def devices(self):
        return {device.device_id: device for device, structure in self.connection.links if self == structure}

    @property
    def away(self):
        return self.simple_status.structures[structure_id].away
    
    @away.setter
    def away(self, is_away):
        self._is_away = is_away
        data = {'away': is_away}

        headers = self.headers.copy()
        headers['Content-Type'] = 'application/json'

        r = requests.post(self.transport_url + '/v1/put/structure.{}'.format(structure_id),
                          data = data,
                          headers = headers)
        
        print r.status_code
        print r.text
        

    def toggle_away(self, structure_id):
        is_away = self.simple_status.structures[structure_id].away
        self.away = not is_away
