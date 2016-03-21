from google.appengine.ext import ndb

class Conversation(ndb.Model):
    convo = ndb.BlobProperty()
    bot = ndb.StringProperty()
    chat_service = ndb.StringProperty()
    uid = ndb.StringProperty()
    
    @classmethod
    def get(cls, bot, chat_service, uid):
        id = "{0} {1} {2}".format(bot, chat_service, uid)
        return cls.get_or_insert(id)

class Bot(ndb.Model):
    owners = ndb.UserProperty()

class Module(ndb.Model):
    owners = ndb.UserProperty()
    data = ndb.JsonProperty()
