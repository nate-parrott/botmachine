import json
from collections import defaultdict
import null_phrase
import parse_example
import random
import commanding
import re
from termcolor import colored
import importlib
import datetime
import pickle
import StringIO

# TODO: give a bonus to previously traversed messages
# TODO: give a bonus to messages with similar fields

SUBSEQUENT_MESSAGE_BONUS = 10
INITIAL_MESSAGE_BONUS = 7
NULL_BONUS = 9
MISSING_FIELDS_BONUS = 0.5

def chain(lists):
    return reduce(lambda a,b: a+b, lists, [])

class Bot(object):
    def __init__(self, json_docs):
        self.initial_message_templates = []
        self.message_templates = {}
        self._last_message_id = 0
        
        for doc in json_docs:
            if 'addon_module' in doc:
                self._current_addon = importlib.import_module(doc['addon_module']).Addon()
            for t in doc['transcripts']:
                self.load_message_thread(t['messages'], True, [])
            self._current_addon = None
        
        self.bots_for_names = {}
        self.convos_with_named_bots = defaultdict(Convo)
        self.log_name = 'bot'
    
    def load_message_thread(self, thread, assume_sender_is_user, parent_messages, condition=None):
        for item in thread:
            if isinstance(item, list):
                # branch:
                final_messages = []
                outbound_assume_sender_is_user = assume_sender_is_user
                for branch in item:
                    outbound_messages, outbound_assume_sender_is_user = self.load_message_thread(branch['messages'], assume_sender_is_user, parent_messages, condition)
                    final_messages += outbound_messages
                parent_messages = final_messages
                assume_sender_is_user = outbound_assume_sender_is_user
                only_enter_if_missing_field = None
            else:
                child_condition = self.condition_from_dict(item)
                if child_condition:
                    branch_parent_messages, _ = self.load_message_thread(item['messages'], assume_sender_is_user, parent_messages, condition=child_condition)
                    parent_messages += branch_parent_messages
                else:
                    sender = item.get('sender', 'user' if assume_sender_is_user else 'bot')
                    run_function = None
                    if 'code' in item:
                        run_function = getattr(self._current_addon, item['code'])
                    id = str(self._last_message_id + 1)
                    self._last_message_id += 1
                    template_msg = TemplateMessage(item.get('text', ''), sender, item.get('id', id), run_function, condition)
                    self.message_templates[template_msg.id] = template_msg
                
                    if len(parent_messages) == 0:
                        self.initial_message_templates.append(template_msg)
                    else:
                        for parent in parent_messages:
                            template_msg.add_parent(parent)
                            
                    assume_sender_is_user = sender != 'user'  
                    parent_messages = [template_msg]
                    only_enter_if_missing_field = None
        
        return parent_messages, assume_sender_is_user
    
    def condition_from_dict(self, item):
        if 'if_missing_field' in item:
            field = item['if_missing_field']
            def fn(convo):
                fields = self.fields_from_convo(convo)
                return field not in fields
            return fn
        return None
    
    def log(self, *args):
        print ' [{0}]'.format(self.log_name), ", ".join(map(str, args))
    
    def interact(self):
        convo_data = self.serialize_convo(Convo())
        while True:
            convo = self.deserialize_convo(convo_data)
            text = raw_input(" > ")
            if text == '': break
            convo_len = len(convo.messages)
            self.send_message_and_get_immediate_response(convo, text)
            for message in convo.messages[convo_len+1:]:
                color = 'blue' if message.sender == 'bot' else 'red'
                print colored(message.text, color)
            convo_data = self.serialize_convo(convo)
    
    def send_message_and_get_immediate_response(self, convo, text):
        parse = self.parse_message(convo, text, 'user')
        convo.append_message(parse)
        self.log("Parsed as:", parse)
        convo_len = len(convo.messages)
        # print " Other examples of this:", u"|".join([x.text() for x in self.examples_for_message_ids[parse.message_id]])
        self.respond(convo)
        
        new_messages = convo.messages[convo_len:]
        responses = [msg for msg in new_messages if msg.sender == 'bot' and msg.text != '' and msg.text[0] != '@']
        if len(responses) != 1:
            self.log("WARNING: bot returned {0} direct responses; expected 1".format(len(responses)))
        return responses[0] if len(responses) else response
    
    def parse_message(self, convo, text, sender):
        # create message-matching bonuses:
        intent_bonuses = {}
        intent_bonuses[''] = NULL_BONUS
        for template in self.initial_message_templates:
            intent_bonuses[template.id] = INITIAL_MESSAGE_BONUS
        
        # which message is this in response to? it's the most recent parseable message sent by the bot
        prompt_messages = [m for m in convo.messages if m.parse and m.sender == 'bot']
        if len(prompt_messages) > 0:
            for child in prompt_messages[-1].template.applicable_children(convo):
                intent_bonuses[child.id] = SUBSEQUENT_MESSAGE_BONUS
        
        # apply penalty to parses that have fields that aren't currently present:
        fields = convo.fields
        for template in self.message_templates.itervalues():
            missing_fields = [field for field in template.required_fields() if field not in fields]
            if len(missing_fields) > 0:
                intent_bonuses[template.id] = MISSING_FIELDS_BONUS ** len(missing_fields)
        
        allowed_intents = set((template.id for template in self.message_templates.itervalues() if template.sender == sender))
        allowed_intents.add('')
        # print self.examples
        
        examples = reduce(lambda a,b: a+b, (t.examples for t in self.message_templates.itervalues())) + null_phrase.examples()
        
        parse = commanding.parse_phrase(text, examples, intent_bonuses=intent_bonuses, allowed_intents=allowed_intents)
        if parse and parse.intent != '':
            msg = ParsedMessage(text, sender, parse, self.message_templates[parse.intent])
        else:
            msg = ParsedMessage(text, sender, None, None)
        return msg
    
    def respond(self, convo):
        # appends responses to convo        
        while convo.messages[-1].sender != 'bot' or convo.messages[-1].text[0] == '@':
            # todo: support scenarios where the bot talks first
            
            if convo.messages[-1].sender == 'bot' and convo.messages[-1].text[0] == '@':
                bot_name = convo.messages[-1].text.split(' ')[0][1:]
                bot_prompt = convo.messages[-1].text[convo.messages[-1].text.index(' ')+1:]
                # the bot just messaged another bot:
                other_bot = self.bot_with_name(bot_name)
                self.log("Asking", convo.messages[-1].text)
                other_bot_response = other_bot.send_message_and_get_immediate_response(self.convos_with_named_bots[bot_name], bot_prompt)
                if other_bot_response:
                    convo.append_message(self.parse_message(convo, other_bot_response.text, bot_name))
                else:
                    self.log("Error: asked @{0}, got no response".format(bot_name))
                    break
            else:
                template = convo.messages[-1].template
                response_template = None
            
                if template:
                    # score responses:
                    fields_present = set(convo.fields.keys())
                    response_templates = template.applicable_children(convo)
                    def score_response(response):
                        fields_to_fill = response.fields_to_fill()
                        unfilled_fields = fields_to_fill - fields_present
                        filled_fields = fields_to_fill & fields_present
                        return -len(unfilled_fields), len(filled_fields)
                    # select all the highest-scoring responses, and collect all their examples:
                    best_score = max(map(score_response, response_templates))
                    response_templates = [t for t in response_templates if score_response(t) == best_score]
                    response_template = random.choice(response_templates)
        
                if response_template:
                    fields = convo.fields
                    if response_template.run_function:
                        child_idx, additional_fields = response_template.run_function(fields)
                        convo.import_fields(additional_fields)
                        response_template = response_template.children[child_idx]
                    
                    response_example = random.choice(response_template.examples)
                    response_filled = response_example.fill_in_fields(fields)
                    text = response_filled.text()
                    convo.append_message(ParsedMessage(text, "bot", response_filled, response_template))
                else:
                    convo.append_message(ParsedMessage("I don't understand", "bot", None, None))        
    
    def bot_with_name(self, name):
        if name not in self.bots_for_names:
            self.bots_for_names[name] = self._bot_with_name(name) 
            self.bots_for_names[name].log_name = name   
        return self.bots_for_names[name]
    
    def _bot_with_name(self, name):
        if name == 'weatherbot':
            files = ['weather_addon.json']
            b = Bot([json.load(open(filename)) for filename in files])
            return b
        print "No bot named", name
    
    def serialize_convo(self, convo):
        def persistent_id(obj):
            if isinstance(obj, TemplateMessage):
                return obj.id
        data = StringIO.StringIO()
        p = pickle.Pickler(data)
        p.persistent_id = persistent_id # TODO: trim the convo length to ~ 20 or so
        p.dump(convo)
        return data.getvalue()
    
    def deserialize_convo(self, data):
        f = StringIO.StringIO(data)
        p = pickle.Unpickler(f)
        def persistent_load(id):
            return self.message_templates.get(id)
        p.persistent_load = persistent_load
        return p.load()

class Convo(object):
    def __init__(self):
        self.messages = []
        self.fields = {}
    
    def append_message(self, message):
        self.messages.append(message)
        if message.parse:
            self.import_fields(message.parse.tags())
    
    def import_fields(self, fields):
        for k,v in fields.iteritems():
            if v is None:
                if k in self.fields:
                    del self.fields[k]
            else:
                self.fields[k] = v

class TemplateMessage(object):
    def __init__(self, text, sender, id, run_function=None, condition=None):
        self.text = text
        self.sender = sender
        self.parents = []
        self.children = []
        self.condition = condition # a function that takes the convo as input
        self.run_function = run_function
        self.id = id
        self.examples = [parse_example.parse_example_to_phrase(self.id, text)]
    
    def applicable_children(self, convo):
        unconditioned = []
        for child in self.children:
            if child.condition:
                if child.condition(convo):
                    return [child]
            else:
                unconditioned.append(child)
        return unconditioned
    
    def add_parent(self, parent):
        parent.children.append(self)
        self.parents.append(parent)
    
    def required_fields(self):
        # the fields that the user has sent us by now
        
        # TODO: predict required fields if we have parent nodes conditioned on getting a specific field
        def intersection_of_sets(sets): return reduce(lambda a,b: a & b, sets, set())
        reqs = intersection_of_sets([p.required_fields() for p in self.parents])
        if self.sender != 'bot':
            reqs = reqs | intersection_of_sets([set(e.tags().keys()) for e in self.examples])
        return reqs
    
    def fields_to_fill(self):
        return set(self.examples[0].tags().iterkeys())
    
    def __repr__(self):
        return u"TemplateMessage({0})".format(self.text)

class ParsedMessage(object):
    def __init__(self, text, sender, parse, template):
        self.text = text
        self.sender = sender
        self.parse = parse
        self.template = template
        self.time = datetime.datetime.now()
    
    def __repr__(self):
        return u"ParsedMessage({0}: {1} -- {2})".format(self.sender, self.parse, self.template)

if __name__ == '__main__':
    # files = ['weather_addon.json']
    files = ['polite.json', 'if_missing_fields.json', 'ask_weather.json']
    # files = ['polite.json', 'lookup_addon.json']
    b = Bot([json.load(open(filename)) for filename in files])
    # b.bot_with_name('weatherbot').interact()
    b.interact()
