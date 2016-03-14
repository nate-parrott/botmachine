from addon import Addon

class Addon(object):
    def weather(self, fields):
        if 'location' in fields:
            return 0, {"weather_conditions": "sunny", "temperature": "59"}
        else:
            return 1, {}
