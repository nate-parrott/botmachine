from addon import BaseAddon

class Addon(BaseAddon):
    def weather(self, fields):
        if 'location' in fields:
            return 0, {"weather_conditions": "sunny", "temperature": "59"}
        else:
            return 1, {}
