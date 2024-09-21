import re

def parse_href(page_url, href):
    if re.match(r'^https?:\/\/\S+$', href):
        return href
    
    if href.startswith('//'):
        base_url = re.match(r'^[^:]+:', page_url).group(0)
        return base_url + href
        
    elif href.startswith('/'):
        base_url = re.match(r'^[^:]+:\/\/[^\/]+', page_url).group(0)
        return base_url + href
    
    else:
        base_url = re.match(r'^.*/', page_url).group(0)
        return base_url + href
