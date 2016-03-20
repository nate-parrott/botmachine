from addon import BaseAddon
import json
import os

class Addon(BaseAddon):
    def lookup_field(self, fields):
        table = self.table(fields['~table'])
        if not table:
            return 1, {}
        
        predicate = self.predicate_fn(fields['predicate'])
        query_val = self.normalize(fields['~query_value'])
        
        scored_rows = []
        for row in table:
            # score = self.fuzzy_match_score(row.get(fields['~query_field']), fields['~query_value'])
            score = predicate(self.normalize(row.get(fields['~query_field'])), query_val)
            if score: scored_rows.append((score, row))
        
        if len(scored_rows) > 0:
            max_score = max((score for score, row in scored_rows))
            rows = [row for score, row in scored_rows if score == max_score]
            value = rows[0].get(fields['~lookup_field'])
            if value:
                return 0, {"~lookup_value": value}
        return 2, {"~lookup_value": None}
    
    def table(self, name):
        path = name + '.table.json'
        if os.path.exists(path):
            return json.load(open(path))
    
    def fuzzy_match_score(self, value, query):
        if value == query:
            return 1
        return 0
    
    # what is the capital where names contains austria in countries
    
    def predicate_fn(self, name):
        if name == 'contains':
            def contains(value, query):
                # print value, query
                if isinstance(value, list) or isinstance(value, dict):
                    return max([self.fuzzy_match_score(self.normalize(member), query) for member in value])
                elif isinstance(value, unicode):
                    return query in value
            return contains
        if name in ('is', 'equals'):
            return self.fuzzy_match_score
        return None
    
    def normalize(self, item):
        if isinstance(item, unicode):
            # TODO: use the tokenizer
            return item.strip().lower()
        return item
            
