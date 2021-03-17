import requests
from bidict import bidict

class CachedEntityClient:

    def __init__(self, api_endpoint, api_token, cache_timeout = 0):
        self.endpoint = f"https://{api_endpoint}/api/v2/entities"
        self.headers = {
            'Authorization': f"Api-Token {api_token}"
        }
        self.cache_timeout = cache_timeout
        self.dimension_name_bidict = bidict()
        self.entities_discovered = []

    def get_entity_name(self, entity_id):
        if entity_id not in self.dimension_name_bidict:
            url = f"{self.endpoint}/{entity_id}"
            resp = requests.get(url, headers = self.headers)

            entity_name = resp.json().get('displayName', entity_id)
            self.dimension_name_bidict.forceput(entity_id, entity_name)
            return entity_name
        else:
            return self.dimension_name_bidict.get(entity_id, entity_id)

    def get_entity_id(self, entity_name):
        entity_id = self.dimension_name_bidict.inverse.get(entity_name, entity_name)
        return entity_id

    def prefetch_entities(self, entity_type, next_page_key=None):
        if entity_type in self.entities_discovered:
            return
        
        url = self.endpoint
        params = {
            "entitySelector": f"type(\"{entity_type.split('.')[-1]}\")"
        }
        if next_page_key is not None:
            params["nextPageKey"] = next_page_key

        resp = requests.get(url, params = params, headers = self.headers).json()

        for entity in resp.get("entities", []):
            self.dimension_name_bidict.forceput(entity.get("entityId"), entity.get("displayName"))

        if resp.get("nextPageKey") is not None:
            self.prefetch_entities(entity_type, resp.get("nextPageKey"))
        else:
            self.entities_discovered.append(entity_type)
        

