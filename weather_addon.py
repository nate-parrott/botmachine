
class Addon(object):
    def weather(self, fields):
        if 'location' in fields:
            return u"weather in {0} is 59 degrees and sunny".format(fields['location'])
        else:
            return u"I don't know where you are."
