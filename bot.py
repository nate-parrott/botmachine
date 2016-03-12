import json
from collections import defaultdict
import null_phrase
import parse_example
import random
import commanding

SUBSEQUENT_MESSAGE_BONUS = 10
INITIAL_MESSAGE_BONUS = 7

def chain(lists):
    return reduce(lambda a,b: a+b, lists, [])

class Bot(object):
    def __init__(self):
        self.initial_message_templates = []
        self.message_templates = {}
    
    def load_json(self, j):
        for t in j['transcripts']:
            self.load_message_thread(t['messages'], True, [])
    
    def load_message_thread(self, thread, assume_sender_is_user, parent_messages):
        for item in thread:
            if 'text' in item:            
                sender = item.get('sender', 'user' if assume_sender_is_user else 'bot')
                template_msg = TemplateMessage(item['text'], sender)
                self.message_templates[template_msg.id] = template_msg
                
                if len(parent_messages) == 0:
                    self.initial_message_templates.append(template_msg)
                else:
                    for parent in parent_messages:
                        template_msg.add_parent(parent)
                            
                assume_sender_is_user = sender != 'user'  
                parent_messages = [template_msg]
            elif 'branches' in item:
                final_messages = []
                for branch in item['branches']:
                    outbound_messages, outbound_assume_sender_is_user = self.load_message_thread(branch['messages'], assume_sender_is_user, parent_messages)
                    final_messages += outbound_messages
                    assume_sender_is_user = outbound_assume_sender_is_user
                parent_messages = final_messages
        
        return parent_messages, assume_sender_is_user
    
    def interact(self):
        convo = []
        while True:
            text = raw_input(" > ")
            if text == '': break
            parse = self.parse_message(convo, text, 'user')
            convo.append(parse)
            print "Parsed as:", parse
            # print " Other examples of this:", u"|".join([x.text() for x in self.examples_for_message_ids[parse.message_id]])
            responses = self.respond(convo)
            for resp in responses:
                print resp.text
            convo += responses
    
    def parse_message(self, convo, text, sender):
        # create message-matching bonuses:
        intent_bonuses = {}
        for template in self.initial_message_templates:
            intent_bonuses[template.id] = INITIAL_MESSAGE_BONUS
        
        # which message is this in response to? it's the most recent parseable message with a different sender
        prompt_messages = [m for m in convo if m.parse and m.sender != sender]
        if len(prompt_messages) > 0:
            for child in prompt_messages[-1].template.children:
                intent_bonuses[child.id] = SUBSEQUENT_MESSAGE_BONUS
        
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
        # todo: support scenarios where the bot talks first
        template = convo[-1].template
        response_templates = template.children
        examples = chain((t.examples for t in response_templates))
        if len(examples):
            response_example = random.choice(examples)
            response_template = self.message_templates[response_example.intent]
            return [ParsedMessage(response_example.text(), "bot", response_example, response_template)]
        else:
            return [ParsedMessage("I don't understand", "bot", None, None)]

_last_message_id = 0

class TemplateMessage(object):
    def __init__(self, text, sender):
        self.text = text
        self.sender = sender
        self.parents = []
        self.children = []
        global _last_message_id
        self.id = str(_last_message_id + 1)
        _last_message_id += 1
        self.examples = [parse_example.parse_example_to_phrase(self.id, text)]
    
    def add_parent(self, parent):
        parent.children.append(self)
        self.parents.append(parent)
    
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
    b = Bot()
    b.load_json(json.load(open('polite.json')))
    b.interact()
