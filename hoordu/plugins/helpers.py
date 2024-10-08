import re

def parse_href(page_url, href):
    if re.match(r'^[a-zA-Z]+:', href):
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

async def unwind_url(http, url, max_iterations=20):
    final_url = url
    
    i = 0
    try:
        while url is not None:
            async with http.head(url, allow_redirects=False, timeout=10) as resp:
                if resp.status // 100 == 3:
                    url = parse_href(url, resp.headers.get('Location'))
                    
                    if url is not None:
                        final_url = url
                else:
                    url = None
                
                i += 1
                if max_iterations is not None and i >= max_iterations:
                    break
            
    except:
        pass
    
    return final_url
