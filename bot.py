import json
from collections import defaultdict
import null_phrase
import parse_example
import random
import commanding
import re
from termcolor import colored
import importlib

SUBSEQUENT_MESSAGE_BONUS = 10
INITIAL_MESSAGE_BONUS = 7
NULL_BONUS = 11
MISSING_FIELDS_BONUS = 0.5

def chain(lists):
    return reduce(lambda a,b: a+b, lists, [])

class Bot(object):
    def __init__(self, json_docs):
        self.initial_message_templates = []
        self.message_templates = {}
        for doc in json_docs:
            if 'addon_module' in doc:
                self._current_addon = importlib.import_module(doc['addon_module']).Addon()
            for t in doc['transcripts']:
                self.load_message_thread(t['messages'], True, [])
            self._current_addon = None
    
    def load_message_thread(self, thread, assume_sender_is_user, parent_messages, condition=None):
        for item in thread:
            if isinstance(item, list):
                # branch:
                final_messages = []
                for branch in item:
                    outbound_messages, outbound_assume_sender_is_user = self.load_message_thread(branch['messages'], assume_sender_is_user, parent_messages, condition)
                    final_messages += outbound_messages
                    assume_sender_is_user = outbound_assume_sender_is_user
                parent_messages = final_messages
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
                    template_msg = TemplateMessage(item.get('text', ''), sender, run_function, condition)
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
    
    def interact(self):
        convo = []
        while True:
            text = raw_input(" > ")
            if text == '': break
            parse = self.parse_message(convo, text, 'user')
            convo.append(parse)
            print "Parsed as:", parse
            convo_len = len(convo)
            # print " Other examples of this:", u"|".join([x.text() for x in self.examples_for_message_ids[parse.message_id]])
            convo = self.respond(convo)
            for message in convo[convo_len:]:
                color = 'blue' if message.sender == 'bot' else 'red'
                print colored(message.text, color)
    
    def parse_message(self, convo, text, sender):
        # create message-matching bonuses:
        intent_bonuses = {}
        intent_bonuses[''] = NULL_BONUS
        for template in self.initial_message_templates:
            intent_bonuses[template.id] = INITIAL_MESSAGE_BONUS
        
        # which message is this in response to? it's the most recent parseable message with a different sender
        prompt_messages = [m for m in convo if m.parse and m.sender != sender]
        if len(prompt_messages) > 0:
            for child in prompt_messages[-1].template.applicable_children(convo):
                intent_bonuses[child.id] = SUBSEQUENT_MESSAGE_BONUS
        
        # apply penalty to parses that have fields that aren't currently present:
        fields = self.fields_from_convo(convo)
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
        convo = convo[:]
        
        while convo[-1].sender != 'bot':
            # todo: support scenarios where the bot talks first
            template = convo[-1].template
            response_template = None
        
            if template:
                # score responses:
                fields_present = set(self.fields_from_convo(convo).keys())
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
                fields = self.fields_from_convo(convo)
                if response_template.run_function:
                    child_idx, additional_fields = response_template.run_function(fields)
                    for k,v in additional_fields.iteritems():
                        fields[k] = v
                    response_template = response_template.children[child_idx]
            
                response_example = random.choice(response_template.examples)
                response_filled = response_example.fill_in_fields(fields)
                text = response_filled.text()
                convo.append(ParsedMessage(text, "bot", response_filled, response_template))
            else:
                convo.append(ParsedMessage("I don't understand", "bot", None, None))
        
        return convo
    
    def fields_from_convo(self, convo):
        fields = {}
        for message in convo:
            if message.parse:
                for k,v in message.parse.tags().iteritems():
                    fields[k] = v
        return fields
    
    def bot_with_name(self, name):
        if name == 'weather':
            files = ['weather_addon.json']
            b = Bot([json.load(open(filename)) for filename in files])
            return b

_last_message_id = 0

class TemplateMessage(object):
    def __init__(self, text, sender, run_function=None, condition=None):
        self.text = text
        self.sender = sender
        self.parents = []
        self.children = []
        self.condition = condition # a function that takes the convo as input
        self.run_function = run_function
        global _last_message_id
        self.id = str(_last_message_id + 1)
        _last_message_id += 1
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
        # TODO: predict required fields if we have parent nodes conditioned on getting a specific field
        # the fields that the user has sent us by now
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
    
    def __repr__(self):
        return u"ParsedMessage({0}: {1} -- {2})".format(self.sender, self.parse, self.template)

if __name__ == '__main__':
    files = ['polite.json', 'weather_addon.json', 'if_missing_fields.json']
    b = Bot([json.load(open(filename)) for filename in files])
    b.interact()
